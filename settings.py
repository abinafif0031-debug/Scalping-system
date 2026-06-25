"""
SYSTEM CONFIGURATION — Intraday Scalping System
"""
import os
from dataclasses import dataclass, field
from typing import List

# ──────────────────────────────────────────────
# API KEYS (set via environment variables)
# ──────────────────────────────────────────────
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
FINNHUB_API_KEY     = os.getenv("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")

# ──────────────────────────────────────────────
# STOCK UNIVERSE
# ──────────────────────────────────────────────
STOCK_UNIVERSE: List[str] = [
    "AAPL", "NVDA", "TSLA", "AMD", "AVGO", "QCOM", "MU", "ORCL", "ADBE", "CRM",
    "NOW", "PANW", "CRWD", "SNOW", "ZS", "OKTA", "AMAT", "LRCX", "KLAC", "NXPI",
    "ON", "GFS", "MPWR", "TER", "TXN", "SMCI", "ARM", "ASML", "ISRG", "SYK",
    "ABT", "JNJ", "TMO", "DHR", "BSX", "MDT", "ZTS", "PG", "HD", "SBUX",
    "NKE", "LULU", "TJX", "AME", "ETN", "EMR", "ITW", "UNP", "UPS", "XPO",
    "JBHT", "CHRW", "ODFL", "EXPD", "ROK", "DOV", "PH", "V", "MA", "SPGI",
    "MSCI", "MCO", "FICO", "CDNS", "SNPS", "ANET", "CSCO", "NTAP", "VRSN",
    "FFIV", "GLW", "TEL", "APH", "KEYS", "GRMN", "MSI", "EQIX", "WELL", "WM",
    "RSG", "GWW", "FAST", "CARR", "OTIS", "TT", "PWR", "PPG", "SHW", "ECL",
    "CL", "CLX", "HSY", "KMB", "MCK", "CIEN", "LLY", "MRK", "GILD", "VRTX",
    "ALNY", "NBIX", "INCY", "DXCM", "IDXX", "ZBRA", "WST", "WAT", "BDX",
    "EW", "A", "APD", "LIN", "XOM", "CVX", "SLB",
    "ALB", "ALGN", "AOS", "APOG", "AR", "ARWR", "AZTA", "AZO", "BBY",
    "BIO", "BIIB", "BKTI", "BLD", "BLDR",
    "SPY", "QQQ",
]

# ──────────────────────────────────────────────
# TIMEFRAMES
# ──────────────────────────────────────────────
TIMEFRAMES = {
    "entry":   "1min",   # entry timing only
    "primary": "5min",   # PRIMARY signal
    "trend":   "15min",  # trend confirmation
    "regime":  "1h",     # market regime
}

CANDLE_COUNT = {
    "1min":  60,
    "5min":  50,
    "15min": 40,
    "1h":    30,
}

# ──────────────────────────────────────────────
# SIGNAL ENGINE
# ──────────────────────────────────────────────
EMA_FAST        = 9
EMA_SLOW        = 21
RSI_PERIOD      = 14
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL     = 9
ATR_PERIOD      = 14
VOLUME_MA_LEN   = 20
VWAP_ANCHOR     = "D"  # daily VWAP reset

# ──────────────────────────────────────────────
# SCORING WEIGHTS (total = 100)
# ──────────────────────────────────────────────
SCORE_WEIGHTS = {
    "trend":     25,
    "momentum":  25,
    "volume":    25,
    "volatility": 25,
}
MIN_SCORE_TO_TRADE = 75

# ──────────────────────────────────────────────
# RISK MANAGEMENT
# ──────────────────────────────────────────────
RISK_PER_TRADE_PCT  = 0.01    # 1% max risk per trade
MAX_DAILY_LOSS_PCT  = 0.02    # -2% → stop all trading
MAX_TRADES_PER_DAY  = 8
TAKE_PROFIT_R_MIN   = 1.5
TAKE_PROFIT_R_MAX   = 3.0
TRAILING_STOP_AFTER = 1.0     # activate trailing after +1R
MAX_CONSECUTIVE_LOSSES = 2

# ──────────────────────────────────────────────
# TRADE HOLDING TIME (minutes)
# ──────────────────────────────────────────────
HOLD_FAST_MIN    = 1
HOLD_FAST_MAX    = 10
HOLD_SMART_MIN   = 10
HOLD_SMART_MAX   = 30
HOLD_INTRADAY_MIN = 30
HOLD_INTRADAY_MAX = 120

# ──────────────────────────────────────────────
# API RATE LIMITS
# ──────────────────────────────────────────────
TWELVE_DATA_RPM       = 144   # requests per minute
BATCH_SIZE_TWELVE     = 8     # symbols per batch request
SCAN_INTERVAL_SECONDS = 120   # scan every 2 minutes

# ──────────────────────────────────────────────
# TRADING HOURS (ET)
# ──────────────────────────────────────────────
MARKET_OPEN_ET  = "09:30"
MARKET_CLOSE_ET = "16:00"
NO_TRADE_AFTER  = "15:30"   # no new positions in last 30 min

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
LOG_DIR        = "logs"
BACKTEST_DIR   = "backtest_results"
STATE_FILE     = "logs/system_state.json"
