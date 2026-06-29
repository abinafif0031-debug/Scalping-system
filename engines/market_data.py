"""
MARKET DATA ENGINE
- Twelve Data API: batch OHLCV candles
- Finnhub API: market movers / filter
- Rate-limit safe: optimized for 144 req/min without burst
"""

import time
import threading
import logging
import requests
from typing import Dict, List, Optional
import pandas as pd

from config.settings import (
    TWELVE_DATA_API_KEY, FINNHUB_API_KEY,
    BATCH_SIZE_TWELVE, TWELVE_DATA_RPM,
    CANDLE_COUNT, TIMEFRAMES
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# GLOBAL THROTTLE (FIXED)
# ──────────────────────────────────────────────
_request_lock = threading.Lock()
_last_request_time = 0

# safe for 144 RPM (with buffer)
MIN_INTERVAL = 0.45  


def throttle_requests():
    global _last_request_time

    with _request_lock:
        now = time.time()
        diff = now - _last_request_time

        if diff < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - diff)

        _last_request_time = time.time()


# ──────────────────────────────────────────────
# Rate Limiter (soft protection)
# ──────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.calls: List[float] = []

    def wait_if_needed(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 60]

        if len(self.calls) >= self.max_per_minute:
            sleep_time = 60 - (now - self.calls[0]) + 0.3
            if sleep_time > 0:
                logger.warning(f"Rate limit hit → sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)

        self.calls.append(time.time())


_twelve_limiter = RateLimiter(TWELVE_DATA_RPM)


# ──────────────────────────────────────────────
# API CALL CORE (FIXED SAFE FLOW)
# ──────────────────────────────────────────────
def fetch_batch_candles(symbols: List[str], interval: str, outputsize: int = 50):
    if not TWELVE_DATA_API_KEY:
        logger.error("TWELVE_DATA_API_KEY not set")
        return {}

    _twelve_limiter.wait_if_needed()
    throttle_requests()

    symbol_str = ",".join(symbols)

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol_str,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
        "order": "ASC",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)

        # ❗ FIX: handle 429 cleanly without retry storm
        if resp.status_code == 429:
            logger.warning(f"429 hit → cooling down API")
            time.sleep(1.5)
            return {}

        resp.raise_for_status()
        data = resp.json()

    except Exception as e:
        logger.error(f"Twelve Data error for {symbol_str}: {e}")
        return {}

    result = {}

    if len(symbols) == 1:
        sym = symbols[0]
        if "values" in data and data.get("status") != "error":
            result[sym] = _parse_twelve_values(data["values"])
    else:
        for sym in symbols:
            sym_data = data.get(sym, {})
            if isinstance(sym_data, dict) and sym_data.get("status") != "error":
                if "values" in sym_data:
                    result[sym] = _parse_twelve_values(sym_data["values"])

    return result


# ──────────────────────────────────────────────
# PARSER
# ──────────────────────────────────────────────
def _parse_twelve_values(values: list) -> pd.DataFrame:
    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[["open", "high", "low", "close", "volume"]].dropna()


# ──────────────────────────────────────────────
# MULTI-TIMEFRAME LOADER (NO STRATEGY CHANGE)
# ──────────────────────────────────────────────
def load_all_timeframes(symbols: List[str]) -> Dict[str, Dict[str, pd.DataFrame]]:
    all_data = {s: {} for s in symbols}

    batches = [
        symbols[i:i + BATCH_SIZE_TWELVE]
        for i in range(0, len(symbols), BATCH_SIZE_TWELVE)
    ]

    # IMPORTANT FIX:
    # add small spacing between timeframe bursts
    for tf_index, (tf_key, tf_interval) in enumerate(TIMEFRAMES.items()):

        outputsize = CANDLE_COUNT.get(tf_interval, 50)

        for b_index, batch in enumerate(batches):

            fetched = fetch_batch_candles(batch, tf_interval, outputsize)

            for sym, df in fetched.items():
                all_data[sym][tf_interval] = df

            # 🔥 prevent burst between batches (CRITICAL FIX)
            time.sleep(0.15)

        # 🔥 prevent burst between timeframes (VERY IMPORTANT)
        time.sleep(0.4)

    return all_data


# ──────────────────────────────────────────────
# FINNHUB (UNCHANGED BUT SAFE)
# ──────────────────────────────────────────────
def get_finnhub_movers():
    if not FINNHUB_API_KEY:
        return {"gainers": [], "losers": []}

    try:
        url = "https://finnhub.io/api/v1/stock/market-status"
        params = {"exchange": "US", "token": FINNHUB_API_KEY}

        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        return {
            "gainers": [],
            "losers": [],
            "market_open": data.get("isOpen", True)
        }

    except Exception as e:
        logger.warning(f"Finnhub error: {e}")
        return {"gainers": [], "losers": [], "market_open": True}


def is_market_open() -> bool:
    return get_finnhub_movers().get("market_open", True)


# ──────────────────────────────────────────────
# PRICE (SAFE)
# ──────────────────────────────────────────────
def get_current_price(symbol: str) -> Optional[float]:
    if not TWELVE_DATA_API_KEY:
        return None

    throttle_requests()

    url = "https://api.twelvedata.com/price"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=8)

        if resp.status_code == 429:
            time.sleep(1.2)
            return None

        data = resp.json()
        return float(data.get("price", 0)) or None

    except Exception as e:
        logger.error(f"Price fetch error {symbol}: {e}")
        return None
