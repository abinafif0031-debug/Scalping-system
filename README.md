# ⚡ Intraday Scalping System
Professional multi-timeframe scalping signal generator for US stocks.

> ⚠️ **DISCLAIMER**: This system generates signals only. It does NOT execute trades automatically. Not financial advice. Past performance does not guarantee future results.

---

## 🏗️ Architecture

```
scalping_system/
├── main.py                    # Entry point
├── demo.py                    # Single-stock live demo
├── config/
│   └── settings.py            # All configuration
├── engines/
│   └── market_data.py         # Twelve Data + Finnhub (batch API)
├── signals/
│   ├── indicators.py          # EMA, VWAP, RSI, MACD, ATR, Volume
│   ├── scorer.py              # 0–100 scoring engine + regime detection
│   └── ai_filter.py           # Claude AI APPROVE/REJECT filter
├── risk/
│   └── manager.py             # Daily loss limit, trade count, position sizing
├── telegram/
│   └── notifier.py            # Signal formatter + Telegram sender
├── backtest/
│   └── runner.py              # Historical simulation
├── logs/                      # Auto-created
└── backtest_results/          # Auto-created
```

---

## 🚀 Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/YOUR_USERNAME/scalping-system.git
cd scalping-system
pip install -r requirements.txt
```

### 2. Configure API Keys
```bash
cp .env.example .env
# Edit .env with your keys
```

Required keys:
| Key | Source | Notes |
|-----|--------|-------|
| `TWELVE_DATA_API_KEY` | [twelvedata.com](https://twelvedata.com) | Free: 800 req/day, 8 req/min |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | Free tier works |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Claude AI filter |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | `/newbot` command |
| `TELEGRAM_CHAT_ID` | [@userinfobot](https://t.me/userinfobot) | Your chat ID |

### 3. Run Live Demo (Single Stock)
```bash
python demo.py AAPL
```
This shows the full pipeline: data → indicators → scoring → AI filter → Telegram preview.

### 4. Run Full System
```bash
python main.py
```

---

## 📊 Signal Logic

### Entry Requirements (ALL must pass)
1. **5min** gives a clear directional signal
2. **15min** confirms the same direction
3. **1hour** regime is NOT sideways
4. Score ≥ 75/100

### Scoring (0–100)
| Component | Max | What it measures |
|-----------|-----|-----------------|
| Trend | 25 | EMA 9/21 alignment, VWAP position, 15m confirmation |
| Momentum | 25 | RSI 50-70 zone, MACD crossover, momentum strengthening |
| Volume | 25 | Volume spike vs 20-bar average |
| Volatility | 25 | ATR within tradeable range (0.3%–2%) |

### Trade Durations
| Mode | Score | Hold Time |
|------|-------|-----------|
| ⚡ Fast Scalp | ≥92 | 1–10 min |
| 🧠 Smart Scalp | ≥82 | 10–30 min |
| 📈 Intraday Hold | ≥75 | 30–120 min |

---

## 🛑 Risk Management
- Risk per trade: 1% of account
- Daily loss limit: -2% → system halts
- Max trades/day: 8
- Stop after 2 consecutive losses
- ATR-based stop loss (1.5× ATR)
- Take profit: 2× risk (R:R = 1:2)

---

## 📩 Telegram Signal Format
```
⚡ TRADE SIGNAL ⚡
━━━━━━━━━━━━━━━━━━━━
📌 AAPL — 🟢 LONG

💰 Entry:       $182.3500
🛑 Stop Loss:   $181.1200
🎯 Take Profit: $184.8100

📊 Confidence: 88.0/100
[████████░░] 88%
  Trend:      22/25
  Momentum:   21/25
  Volume:     25/25
  Volatility: 20/25

📈 Market Regime: BULLISH
⏱ Timeframes: 15m✅ | 1h:bullish✅ | 1m✅
⏳ Duration: 🧠 Smart Scalp (10–30 min)

💡 Reason: EMA cross + above VWAP + MACD bullish + vol spike x2.3
🤖 AI: Signal logic consistent with bullish regime

⚠️ SIGNALS ONLY — Not financial advice
```

---

## 📉 Backtest

```bash
# Backtest single symbol
python backtest/runner.py AAPL

# Output example:
# total_trades  : 47
# win_rate      : 63.8%
# avg_win_r     : 1.87R
# avg_loss_r    : -0.94R
# avg_rr_ratio  : 1.99
# max_drawdown  : -8.2%
# total_return  : +31.4%
```

---

## ☁️ GitHub Setup

```bash
git init
git add .
git commit -m "Initial commit: scalping system v1.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/scalping-system.git
git push -u origin main
```

---

## 🚂 Railway Deployment

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Connect your repository
3. Add environment variables (Settings → Variables):
   ```
   TWELVE_DATA_API_KEY=...
   FINNHUB_API_KEY=...
   ANTHROPIC_API_KEY=...
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   ```
4. Deploy → Railway runs `python main.py` 24/7
5. View logs in Railway dashboard

The `railway.toml` file handles auto-restart on failure.

---

## ⚙️ Configuration

Edit `config/settings.py` to tune:
- `MIN_SCORE_TO_TRADE` — default 75
- `MAX_TRADES_PER_DAY` — default 8
- `MAX_DAILY_LOSS_PCT` — default 2%
- `SCAN_INTERVAL_SECONDS` — default 120s
- `BATCH_SIZE_TWELVE` — default 8 symbols/request

---

## 🔌 API Rate Limits

| API | Limit | How we stay safe |
|-----|-------|-----------------|
| Twelve Data | 144 req/min | Batch 8 symbols per request, RateLimiter class |
| Finnhub | 60 req/min | Used sparingly (market status only) |
| Claude API | Standard | Called once per qualifying signal only |
| Telegram | 30 msg/min | Max 8 signals/day, far below limit |
