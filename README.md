# TW Stocker v7 — AI 量化交易系統

中期橫截面動量策略，流動性 Universe 排名 + 事件驅動回測 + ATR 停利停損。
經 Walk-Forward 驗證、100+ 組參數掃描、2000 次 Block Bootstrap Monte Carlo 壓力測試。

📊 **線上報表**：https://voidful.github.io/tw_stocker/stock_report.html

## 績效總覽（含滑價 10bps + Gap-Aware Fill）

| 指標 | 值 | 說明 |
|------|:---:|------|
| **Sharpe** | **2.96** | 含 10bps 滑價的誠實回測 |
| **年化報酬** | **+91.4%** | 包含交易成本 + 滑價 |
| **MDD** | **-18.4%** | Gap-aware stop fill |
| **Calmar** | **4.96** | 年化報酬/MDD |
| **Profit Factor** | **2.25** | 總獲利/總虧損 |
| **勝率** | **61.1%** | 473 筆交易 |

### v7 vs v6 變化（回測誠實化）

| 指標 | v6 (slippage=0) | **v7 (honest)** | 差異 |
|------|:---------------:|:---------------:|:----:|
| Sharpe | 3.12 | **2.96** | -5% |
| MDD | -17.7% | **-18.4%** | +0.7% |
| 年化 | +96.6% | **+91.4%** | -5.2% |

> v7 的績效下降來自回測誠實化（滑價 + gap-aware fill），不是策略劣化。

### Monte Carlo 壓力測試（Block Bootstrap, 2000x）

| 情境 | 最差 5% 報酬 | 最差 5% MDD |
|------|:----------:|:-----------:|
| 全體 (block=5) | +293% | -17.5% |
| 保守 (勝率50%) | -5.5% | -43.8% |

> Block bootstrap 保留時序結構（連續虧損、相關性上升），比 iid 更接近真實尾部風險。

## 策略公式

```
每日訊號:
  1. Universe = 過去 20 日平均成交額 Top-50
  2. 綜合評分 = rank_momentum(20d) × 3 + rank_trend(60MA) × 1
  3. 進場: score ≥ 2.0 AND close > 60MA AND 大盤 > 60MA
  4. 跳空 > 1.5×ATR 的進場日跳過
  5. Top-5 選股（相關性 > 0.8 的替換為不相關候選）

出場 (gap-aware):
  - 停損: min(stop_price, open)  ← 隔夜跳空用開盤價
  - 停利: max(tp_price, open)    ← 跳空有利用開盤價
  - 時間: 20 個交易日強制出場

成本: 買 0.1425% + 賣 0.4425% + 滑價 10bps
```

## 快速開始

```bash
pip install -r requirements.txt

# v7 誠實回測（gap-aware + slippage 10bps）
python ai_report.py

# 比對舊版（無滑價，用於對比）
python ai_report.py --slippage 0

# Block Bootstrap 壓力測試
python monte_carlo.py --runs 2000 --block-size 5
```

## CLI 參數

### 核心（已鎖定）
| 參數 | 預設值 | 說明 |
|---|:---:|---|
| `--tp-atr` | `4.0` | ATR 停利倍數 |
| `--sl-atr` | `3.0` | ATR 停損倍數 |
| `--top-k` | `5` | 每日最多進場股票數 |
| `--hold-days` | `20` | 最大持倉交易日 |
| `--gap-filter` | `1.5` | 跳空過濾 ATR 倍數 |
| `--regime-filter` | `true` | 大盤過濾 (0050 > 60MA) |
| `--corr-filter` | `0.8` | 去除高度相關持倉 |
| `--slippage` | `0.001` | 滑價 10bps（v7 新增） |

### 可選風控（opt-in, 經實測驗證效果）
| 參數 | 預設值 | 實測結果 |
|---|:---:|---|
| `--sector-max-pct` | `1.0` | 0.5 可壓 MDD 至 -16.0% (Sharpe 持平) |
| `--max-heat` | `1.0` | 2% 過緊 (97 筆); 需進一步研究 |
| `--rank-weight` | `false` | 有害: Sharpe -27% |
| `--regime-delev` | `false` | 有害: Sharpe -32%, 錯過反彈 |
| `--dynamic-risk` | `false` | 中性: Sharpe ±2% |

### 已驗證無效（永久排除）
| 功能 | 影響 |
|------|------|
| `--breakeven` | Sharpe → 0.48 ☠️ |
| `--trailing` | Sharpe → ~0.08 ☠️ |
| `--ml-weights` | Sharpe -55% |
| `--rank-weight` | Sharpe -27% |

## v7 回測誠實化 — 技術細節

### Gap-Aware Stop Fill
```
v6: exit_price = stop_price          (永遠成交在停損價)
v7: exit_price = min(stop_price, open)  (gap down 用開盤價，更接近實盤)
```
實測影響：Sharpe 3.12 → 3.11 (幾乎為零，代表大部分停損沒有被 gap 穿越)

### Block Bootstrap Monte Carlo
```
v6: random.choices(trades, k=n)       (打散時序，忽略連續虧損)
v7: block_bootstrap(trades, block=5)  (保留一週的連續性)
```
結果：最差 5% MDD 從 -12.5% 惡化到 -17.5%（更接近真實尾部風險）

### 11 組完整消融測試結果
| Config | Sharpe | MDD | 年化 | 交易 |
|--------|:------:|:---:|:----:|:----:|
| v6 base | 3.12 | -17.7% | +97% | 471 |
| + gap-aware | 3.11 | -17.7% | +96% | 470 |
| **+ slippage** | **2.94** | **-18.4%** | **+91%** | **472** |
| + rank weight | 2.26 | -25.9% | +71% | 461 |
| + heat 2% | 0.84 | -21.1% | +11% | 97 |
| + regime delev | 2.11 | -23.9% | +66% | 470 |

## 專案結構

```
tw_stocker/
├── ai_report.py              # 主程式 + CLI + HTML 報表 (v7)
├── sweep.py                  # 季度參數校準 + 劣化警報 + Telegram
├── walk_forward.py           # Walk-Forward 穩定性驗證
├── monte_carlo.py            # Block Bootstrap 壓力測試 v3
├── paper_trade.py            # Paper Trading + Telegram 通知
├── strategy/
│   ├── ai_strategy.py        # 因子工程 (Mom×3 + Trend×1)
│   ├── event_backtest.py     # 事件驅動回測 + gap-aware fill + 風控
│   ├── risk_metrics.py       # 風險指標計算
│   └── benchmark.py          # Benchmark (0050 / EW)
├── artifacts/                # 每日 CSV
├── .github/workflows/
│   └── update_ai_report.yml  # 每日 + 季度自動執行
└── stock_report.html         # 完整交易報表 (v7)
```

## 免責聲明

本系統由 AI 量化模型自動產出，僅供學術研究與技術交流之用，不構成任何投資建議。歷史回測績效不代表未來實際報酬，投資有風險，決策請自行負責。
