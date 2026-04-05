#!/usr/bin/env python3
"""
Walk-Forward 驗證腳本

將回測期間切成滾動窗口，驗證策略在每個 out-of-sample 段都穩定。
這是過擬合檢測的黃金標準。

使用方式:
  python walk_forward.py                # 預設 4 段 rolling
  python walk_forward.py --folds 6      # 6 段更細粒度
  python walk_forward.py --oos-days 200 # OOS 段改 200 天
"""

import subprocess
import re
import sys
import argparse
from datetime import datetime


def run_backtest(days, extra_args=''):
    """Run ai_report.py and extract metrics."""
    cmd = f'python ai_report.py --days {days} {extra_args}'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
    out = r.stdout + r.stderr

    def get(pattern, default=0):
        m = re.search(pattern, out)
        return float(m.group(1)) if m else default

    return {
        'ann': get(r'年化報酬率:\s+([\+\-\d\.]+)%'),
        'sharpe': get(r'Sharpe Ratio:\s+([\+\-\d\.]+)'),
        'sortino': get(r'Sortino Ratio:\s+([\+\-\d\.]+)'),
        'calmar': get(r'Calmar Ratio:\s+([\+\-\d\.]+)'),
        'mdd': get(r'最大回撤:\s+([\+\-\d\.]+)%'),
        'trades': int(get(r'共 (\d+) 筆交易')),
        'win_rate': get(r'勝率\s*([\d\.]+)%'),
        'pf': get(r'Profit Factor:\s+([\d\.]+)'),
    }


def main():
    parser = argparse.ArgumentParser(description='Walk-Forward 驗證')
    parser.add_argument('--folds', type=int, default=4, help='滾動窗口段數 (預設 4)')
    parser.add_argument('--total-days', type=int, default=1500, help='總回測天數')
    parser.add_argument('--oos-days', type=int, default=300, help='每段 OOS 天數 (預設 300)')
    args = parser.parse_args()

    print(f"📊 Walk-Forward 驗證 — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"   總天數: {args.total_days} | 段數: {args.folds} | OOS: {args.oos_days}天/段")
    print()

    # 計算每段窗口
    # Window N: days = total - (folds - N) * oos_days
    # 最早段用最長的 days（包含最多歷史），最近段用最短
    windows = []
    for fold in range(args.folds):
        total_for_fold = args.total_days - fold * args.oos_days
        if total_for_fold < 400:  # 至少 400 天才有意義
            break
        label = f"Fold {fold+1}"
        windows.append((label, total_for_fold))

    # 也跑全量做對照
    windows.append(("Full (1200d)", 1200))

    # 加入 slippage 壓力測試
    windows.append(("Full+slip0.1%", 1200))

    header = f"{'Window':<18s} | {'Days':>5s} | {'Ann':>7s} | {'Sharpe':>6s} | {'Sort':>5s} | {'Calmar':>6s} | {'MDD':>7s} | {'#Tr':>4s} | {'WR':>5s} | {'PF':>4s}"
    sep = '-' * len(header)
    print(header)
    print(sep)

    sharpes = []
    for i, (label, days) in enumerate(windows):
        sys.stderr.write(f'[{i+1}/{len(windows)}] {label} ({days}d)...\n')
        sys.stderr.flush()

        extra = '--slippage 0.001' if 'slip' in label else ''
        metrics = run_backtest(days, extra)

        if 'slip' not in label and label != 'Full (1200d)':
            sharpes.append(metrics['sharpe'])

        print(f"{label:<18s} | {days:>5d} | {metrics['ann']:>+6.1f}% | {metrics['sharpe']:>6.3f} | "
              f"{metrics['sortino']:>5.2f} | {metrics['calmar']:>6.3f} | {metrics['mdd']:>6.1f}% | "
              f"{metrics['trades']:>4d} | {metrics['win_rate']:>4.1f}% | {metrics['pf']:>4.2f}")

    print(sep)

    # 穩定性統計
    if sharpes:
        import statistics
        avg_sh = statistics.mean(sharpes)
        min_sh = min(sharpes)
        max_sh = max(sharpes)
        std_sh = statistics.stdev(sharpes) if len(sharpes) > 1 else 0
        print(f"\n📈 Walk-Forward 穩定性統計 (OOS 段)")
        print(f"   平均 Sharpe: {avg_sh:.3f}")
        print(f"   最低 Sharpe: {min_sh:.3f}")
        print(f"   最高 Sharpe: {max_sh:.3f}")
        print(f"   標準差:      {std_sh:.3f}")
        print(f"   穩定性比:    {avg_sh / (std_sh + 1e-8):.2f} (>3 = 優秀)")

        if min_sh >= 1.5:
            print("\n✅ 所有窗口 Sharpe >= 1.5，策略穩定性極佳")
        elif min_sh >= 1.0:
            print("\n⚠️  部分窗口 Sharpe 低於 1.5，需觀察")
        else:
            print("\n🚨 有窗口 Sharpe < 1.0，可能存在過擬合風險")


if __name__ == '__main__':
    main()
