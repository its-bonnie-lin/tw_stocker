#!/usr/bin/env python3
"""
Paper Trading 比對工具

每日收盤後比對 AI 策略信號與實際成交紀錄，追蹤回測 vs 實盤偏差。

使用方式:
  # 1. 產出今日信號
  python paper_trade.py signals

  # 2. 記錄實際成交（手動輸入）
  python paper_trade.py log --ticker 2330 --action buy --price 980 --shares 1000

  # 3. 比對報告
  python paper_trade.py report
"""

import json
import os
import sys
from datetime import datetime, date
import argparse


TRADE_LOG = 'paper_trades.json'
SIGNAL_LOG = 'paper_signals.json'


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def generate_signals(args):
    """從最新 stock_report.html 擷取今日執行計畫。"""
    import re

    report_path = 'stock_report.html'
    if not os.path.exists(report_path):
        print("⚠️ stock_report.html 不存在，請先執行 python ai_report.py")
        return

    with open(report_path) as f:
        html = f.read()

    # 從 HTML 擷取「今日執行計畫」區塊
    # 搜尋交易計畫表格中的股票
    pattern = r'<td>(\d{4})</td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.]+)</td>\s*<td[^>]*>([\d\.]+)</td>'
    matches = re.findall(pattern, html)

    if not matches:
        # 嘗試另一種格式
        pattern = r'買入\s+(\d{4})\s'
        tickers = re.findall(pattern, html)
        if tickers:
            print(f"📋 今日信號股票: {', '.join(tickers)}")
        else:
            print("📋 今日無信號（可能為非交易日或 regime filter 阻擋）")
        return

    today = date.today().isoformat()
    signals = load_json(SIGNAL_LOG)

    print(f"📋 今日執行信號 ({today}):")
    print(f"{'股票':>6s} | {'進場價':>8s} | {'停利價':>8s} | {'停損價':>8s}")
    print("-" * 40)

    new_signals = []
    for ticker, entry, tp, sl in matches:
        print(f"{ticker:>6s} | {entry:>8s} | {tp:>8s} | {sl:>8s}")
        new_signals.append({
            'date': today,
            'ticker': ticker,
            'entry_price': float(entry),
            'tp_price': float(tp),
            'sl_price': float(sl),
            'status': 'pending',
        })

    if new_signals:
        signals.extend(new_signals)
        save_json(SIGNAL_LOG, signals)
        print(f"\n✅ {len(new_signals)} 筆信號已記錄到 {SIGNAL_LOG}")


def log_trade(args):
    """記錄實際成交。"""
    trades = load_json(TRADE_LOG)
    trade = {
        'date': date.today().isoformat(),
        'ticker': args.ticker,
        'action': args.action,
        'price': args.price,
        'shares': args.shares,
        'timestamp': datetime.now().isoformat(),
    }
    trades.append(trade)
    save_json(TRADE_LOG, trades)
    print(f"✅ 已記錄: {args.action.upper()} {args.ticker} @ {args.price} × {args.shares}")


def generate_report(args):
    """比對信號 vs 實際成交。"""
    signals = load_json(SIGNAL_LOG)
    trades = load_json(TRADE_LOG)

    if not signals:
        print("⚠️ 無信號記錄，先執行 python paper_trade.py signals")
        return

    print(f"📊 Paper Trading 比對報告")
    print(f"   信號記錄: {len(signals)} 筆")
    print(f"   實際成交: {len(trades)} 筆")
    print()

    # 按日統計
    dates = sorted(set(s['date'] for s in signals))

    total_signals = 0
    total_executed = 0
    total_slippage = []

    for d in dates:
        day_signals = [s for s in signals if s['date'] == d]
        day_trades = [t for t in trades if t['date'] == d]

        total_signals += len(day_signals)
        signal_tickers = {s['ticker'] for s in day_signals}
        trade_tickers = {t['ticker'] for t in day_trades if t['action'] == 'buy'}

        executed = signal_tickers & trade_tickers
        missed = signal_tickers - trade_tickers
        extra = trade_tickers - signal_tickers

        total_executed += len(executed)

        # 計算滑價
        for t in day_trades:
            if t['action'] == 'buy' and t['ticker'] in signal_tickers:
                sig = next(s for s in day_signals if s['ticker'] == t['ticker'])
                slip = (t['price'] - sig['entry_price']) / sig['entry_price'] * 100
                total_slippage.append(slip)

        print(f"📅 {d}: {len(day_signals)} 信號 | {len(executed)} 執行 | {len(missed)} 未執行 | {len(extra)} 額外")
        if missed:
            print(f"   ❌ 未執行: {', '.join(missed)}")
        if extra:
            print(f"   ⚠️ 額外交易: {', '.join(extra)}")

    print()
    execution_rate = total_executed / total_signals * 100 if total_signals > 0 else 0
    print(f"📈 執行統計:")
    print(f"   執行率:     {execution_rate:.1f}% ({total_executed}/{total_signals})")

    if total_slippage:
        import statistics
        avg_slip = statistics.mean(total_slippage)
        print(f"   平均滑價:   {avg_slip:+.3f}%")
        print(f"   最大滑價:   {max(total_slippage):+.3f}%")
        if abs(avg_slip) < 0.1:
            print("   ✅ 滑價在可接受範圍內")
        elif abs(avg_slip) < 0.3:
            print("   ⚠️ 滑價偏高，建議調整進場時機")
        else:
            print("   🚨 滑價過大，需檢查執行流程")


def main():
    parser = argparse.ArgumentParser(description='Paper Trading 比對工具')
    subparsers = parser.add_subparsers(dest='command', help='commands')

    # signals
    subparsers.add_parser('signals', help='擷取今日信號')

    # log
    log_parser = subparsers.add_parser('log', help='記錄實際成交')
    log_parser.add_argument('--ticker', required=True, help='股票代號')
    log_parser.add_argument('--action', choices=['buy', 'sell'], required=True)
    log_parser.add_argument('--price', type=float, required=True, help='成交價')
    log_parser.add_argument('--shares', type=int, required=True, help='股數')

    # report
    subparsers.add_parser('report', help='比對報告')

    args = parser.parse_args()

    if args.command == 'signals':
        generate_signals(args)
    elif args.command == 'log':
        log_trade(args)
    elif args.command == 'report':
        generate_report(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
