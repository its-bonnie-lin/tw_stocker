#!/usr/bin/env python3
"""
Monte Carlo 壓力測試 v2

對歷史交易做 bootstrap 重採樣，估算策略在極端情境下的表現分布。
新增 regime-aware 分析：分開統計多頭/空頭期交易表現。

使用方式:
  python monte_carlo.py                # 預設 2000 次模擬
  python monte_carlo.py --runs 5000    # 更精確
  python monte_carlo.py --confidence 99  # 99% 信心區間
"""

import subprocess
import re
import sys
import argparse
import random
import statistics
from datetime import datetime


def get_trades():
    """從最新 trades CSV 取得交易列表（含日期）。"""
    import csv
    import os
    import glob

    csv_files = glob.glob('artifacts/trades_*.csv')
    if not csv_files:
        print("📥 執行回測以取得交易數據...")
        subprocess.run('python ai_report.py', shell=True, capture_output=True, text=True, timeout=180)
        csv_files = glob.glob('artifacts/trades_*.csv')
        if not csv_files:
            print("❌ 無法取得交易數據")
            sys.exit(1)

    latest = max(csv_files, key=os.path.getmtime)
    print(f"   讀取 {latest}...")
    trades = []
    with open(latest) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                trades.append({
                    'return': float(row['Return_Pct']),
                    'entry_date': row.get('Entry_Date', ''),
                    'reason': row.get('Reason', ''),
                })
            except (KeyError, ValueError):
                continue

    return trades


def simulate_equity(returns, initial=1_000_000, position_size=0.10):
    """用隨機重採樣的交易序列模擬權益曲線。"""
    equity = initial
    peak = initial
    max_dd = 0

    for ret in returns:
        trade_pnl = equity * position_size * ret
        equity += trade_pnl
        peak = max(peak, equity)
        dd = (equity - peak) / peak
        max_dd = min(max_dd, dd)

    total_return = (equity / initial - 1)
    return total_return, max_dd, equity


def run_mc(returns, n_runs, label=""):
    """Run Monte Carlo and return stats dict."""
    n = len(returns)
    all_returns = []
    all_mdds = []

    for _ in range(n_runs):
        sample = random.choices(returns, k=n)
        ret, mdd, _ = simulate_equity(sample)
        all_returns.append(ret)
        all_mdds.append(mdd)

    all_returns.sort()
    all_mdds.sort()

    return {
        'label': label,
        'n': n,
        'median_ret': statistics.median(all_returns),
        'p5_ret': all_returns[int(n_runs * 0.05)],
        'p95_ret': all_returns[int(n_runs * 0.95)],
        'median_mdd': statistics.median(all_mdds),
        'p5_mdd': all_mdds[int(n_runs * 0.05)],
    }


def main():
    parser = argparse.ArgumentParser(description='Monte Carlo 壓力測試 v2')
    parser.add_argument('--runs', type=int, default=2000, help='模擬次數 (預設 2000)')
    parser.add_argument('--confidence', type=int, default=95, help='信心區間 (預設 95)')
    args = parser.parse_args()

    trades = get_trades()
    returns = [t['return'] for t in trades]
    n_trades = len(returns)

    if n_trades < 30:
        print(f"⚠️ 交易筆數 {n_trades} 太少")
        sys.exit(1)

    print(f"\n📊 Monte Carlo 壓力測試 v2 — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"   交易筆數: {n_trades}")
    print(f"   模擬次數: {args.runs}")

    # 原始序列
    orig_ret, orig_mdd, _ = simulate_equity(returns)
    print(f"\n📈 原始序列: 報酬 {orig_ret*100:+.1f}% | MDD {orig_mdd*100:.1f}%")

    # === 全體 Monte Carlo ===
    print(f"\n🎲 全體交易 Monte Carlo ({n_trades} 筆)...")
    all_stats = run_mc(returns, args.runs, "全體")

    # === Regime 分割 ===
    # 用交易結果分：正報酬 vs 負報酬（模擬多頭/空頭 regime）
    win_trades = [t['return'] for t in trades if t['return'] > 0]
    loss_trades = [t['return'] for t in trades if t['return'] <= 0]

    # 停利 vs 停損 vs 時間到期
    tp_trades = [t['return'] for t in trades if t['reason'] == '停利']
    sl_trades = [t['return'] for t in trades if t['reason'] == '停損']
    time_trades = [t['return'] for t in trades if t['reason'] == '時間到期']

    print(f"\n📊 交易分類:")
    print(f"   獲利: {len(win_trades)} 筆 (平均 {statistics.mean(win_trades)*100:+.1f}%)")
    print(f"   虧損: {len(loss_trades)} 筆 (平均 {statistics.mean(loss_trades)*100:+.1f}%)")
    if tp_trades:
        print(f"   停利: {len(tp_trades)} 筆 (平均 {statistics.mean(tp_trades)*100:+.1f}%)")
    if sl_trades:
        print(f"   停損: {len(sl_trades)} 筆 (平均 {statistics.mean(sl_trades)*100:+.1f}%)")
    if time_trades:
        print(f"   到期: {len(time_trades)} 筆 (平均 {statistics.mean(time_trades)*100:+.1f}%)")

    # === 最差情境：只用虧損交易做 MC（熊市壓力測試）===
    bear_stats = None
    if len(loss_trades) >= 20:
        print(f"\n🐻 熊市壓力測試 (僅虧損交易 {len(loss_trades)} 筆)...")
        bear_stats = run_mc(loss_trades, args.runs, "熊市")

    # === 保守情境：50% 獲利 + 50% 虧損（降低勝率）===
    mixed = loss_trades + random.choices(win_trades, k=len(loss_trades))
    print(f"\n⚖️ 保守情境 (勝率降至 50%, {len(mixed)} 筆)...")
    conservative_stats = run_mc(mixed, args.runs, "保守")

    # === 輸出報告 ===
    tail = (100 - args.confidence) / 100

    print(f"\n{'='*70}")
    print(f"{'情境':<12s} | {'筆數':>4s} | {'最差 5% 報酬':>12s} | {'中位數報酬':>10s} | {'最差 5% MDD':>11s}")
    print(f"{'-'*70}")

    for s in [all_stats, conservative_stats, bear_stats]:
        if s is None:
            continue
        print(f"{s['label']:<12s} | {s['n']:>4d} | {s['p5_ret']*100:>+10.1f}% | {s['median_ret']*100:>+8.1f}% | {s['p5_mdd']*100:>9.1f}%")

    print(f"{'='*70}")

    # 風險評估
    print(f"\n📊 風險評估:")
    worst_mdd = all_stats['p5_mdd']
    if abs(worst_mdd) < 0.22:
        print(f"   ✅ 全體最差 5% MDD = {worst_mdd*100:.1f}% < -22%，風險可控")
    else:
        print(f"   ⚠️ 全體最差 5% MDD = {worst_mdd*100:.1f}%，需注意")

    if conservative_stats['p5_ret'] > 0:
        print(f"   ✅ 保守情境（勝率50%）最差 5% 報酬仍為正 ({conservative_stats['p5_ret']*100:+.1f}%)")
    else:
        print(f"   ⚠️ 保守情境最差 5% 報酬為負 ({conservative_stats['p5_ret']*100:+.1f}%)")

    # 實盤建議
    print(f"\n💡 實盤建議:")
    print(f"   預期 MDD: {all_stats['median_mdd']*100:.1f}% ~ {worst_mdd*100:.1f}%")
    suggested = 100000 / abs(worst_mdd) if worst_mdd != 0 else 100000
    print(f"   建議起始資金: ≥ {suggested:,.0f} 元")


if __name__ == '__main__':
    main()
