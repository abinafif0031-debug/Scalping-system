"""
SYSTEM CONFIGURATION — Intraday Scalping System
"""
import os
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
    "entry":   "1min",
    "primary": "5min",
    "trend":   "15min",
    "regime":  "1h",
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
VWAP_ANCHOR     = "D"

# ──────────────────────────────────────────────
# SCORING WEIGHTS (total = 100)
# ──────────────────────────────────────────────
SCORE_WEIGHTS = {
    "trend":      25,
    "momentum":   25,
    "volume":     25,
    "volatility": 25,
}

# ──────────────────────────────────────────────
# SCORE THRESHOLDS PER SESSION
# ──────────────────────────────────────────────
MIN_SCORE_PRE_MARKET   = 88   # صارم جداً في البري
MIN_SCORE_OPEN_MARKET  = 78   # الأوبن ماركت
MIN_SCORE_TO_TRADE     = 78   # الافتراضي (يُستبدل حسب الجلسة)

# ──────────────────────────────────────────────
# RISK MANAGEMENT
# ──────────────────────────────────────────────
RISK_PER_TRADE_PCT     = 0.01
MAX_DAILY_LOSS_PCT     = 0.02
MAX_CONSECUTIVE_LOSSES = 2
TAKE_PROFIT_R_MIN      = 1.5
TAKE_PROFIT_R_MAX      = 3.0
TRAILING_STOP_AFTER    = 1.0

# ──────────────────────────────────────────────
# TRADE LIMITS PER SESSION
# ──────────────────────────────────────────────
MAX_TRADES_PRE_MARKET  = 3    # حد البري ماركت
MAX_TRADES_OPEN_MARKET = 13   # حد الأوبن ماركت
MAX_TRADES_PER_DAY     = MAX_TRADES_PRE_MARKET + MAX_TRADES_OPEN_MARKET  # 16 إجمالي

# ──────────────────────────────────────────────
# TRADING HOURS (ET)
# ──────────────────────────────────────────────
PRE_MARKET_START_ET = "08:00"   # بداية البري ماركت
PRE_MARKET_END_ET   = "09:29"   # نهاية البري ماركت
MARKET_OPEN_ET      = "09:30"   # افتتاح السوق
NO_TRADE_AFTER      = "15:30"   # لا صفقات بعد هذا الوقت

# ──────────────────────────────────────────────
# TRADE HOLDING TIME (minutes)
# ──────────────────────────────────────────────
HOLD_FAST_MIN     = 1
HOLD_FAST_MAX     = 10
HOLD_SMART_MIN    = 10
HOLD_SMART_MAX    = 30
HOLD_INTRADAY_MIN = 30
HOLD_INTRADAY_MAX = 120

# ──────────────────────────────────────────────
# API RATE LIMITS
# ──────────────────────────────────────────────
TWELVE_DATA_RPM       = 144
BATCH_SIZE_TWELVE     = 8
SCAN_INTERVAL_SECONDS = 120

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
LOG_DIR      = "logs"
BACKTEST_DIR = "backtest_results"
STATE_FILE   = "logs/system_state.json"
