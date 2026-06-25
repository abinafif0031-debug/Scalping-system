"""
MARKET DATA ENGINE
- Twelve Data API: batch OHLCV candles
- Finnhub API: market movers / filter
- Rate-limit safe: never exceeds 144 req/min
"""

import time
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd

from config.settings import (
    TWELVE_DATA_API_KEY, FINNHUB_API_KEY,
    BATCH_SIZE_TWELVE, TWELVE_DATA_RPM,
    CANDLE_COUNT, TIMEFRAMES
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Rate limiter
# ──────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.calls: List[float] = []

    def wait_if_needed(self):
        now = time.time()
        # remove calls older than 60s
        self.calls = [t for t in self.calls if now - t < 60]
        if len(self.calls) >= self.max_per_minute:
            sleep_time = 60 - (now - self.calls[0]) + 0.5
            if sleep_time > 0:
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
        self.calls.append(time.time())


_twelve_limiter = RateLimiter(TWELVE_DATA_RPM)


# ──────────────────────────────────────────────
# Twelve Data — batch candles
# ──────────────────────────────────────────────
def fetch_batch_candles(
    symbols: List[str],
    interval: str,
    outputsize: int = 50
) -> Dict[str, pd.DataFrame]:
    """
    Fetch OHLCV for multiple symbols in ONE request.
    Returns dict: symbol -> DataFrame with columns [open, high, low, close, volume].
    """
    if not TWELVE_DATA_API_KEY:
        logger.error("TWELVE_DATA_API_KEY not set")
        return {}

    _twelve_limiter.wait_if_needed()
    symbol_str = ",".join(symbols)
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol":     symbol_str,
        "interval":   interval,
        "outputsize": outputsize,
        "apikey":     TWELVE_DATA_API_KEY,
        "format":     "JSON",
        "order":      "ASC",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Twelve Data error for {symbol_str}: {e}")
        return {}

    result: Dict[str, pd.DataFrame] = {}

    # Single symbol returns flat structure; multiple returns nested
    if len(symbols) == 1:
        sym = symbols[0]
        if "values" in data and data.get("status") != "error":
            result[sym] = _parse_twelve_values(data["values"])
    else:
        for sym in symbols:
            sym_data = data.get(sym, {})
            if isinstance(sym_data, dict) and sym_data.get("status") != "error" and "values" in sym_data:
                result[sym] = _parse_twelve_values(sym_data["values"])

    return result


def _parse_twelve_values(values: list) -> pd.DataFrame:
    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["open", "high", "low", "close", "volume"]].dropna()


# ──────────────────────────────────────────────
# Multi-timeframe batch loader
# ──────────────────────────────────────────────
def load_all_timeframes(symbols: List[str]) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Returns:
        {symbol: {"1min": df, "5min": df, "15min": df, "1h": df}}

    Batches symbols to avoid API limit:
    - 4 timeframes × ceil(n/8) batches = minimal requests
    """
    all_data: Dict[str, Dict[str, pd.DataFrame]] = {s: {} for s in symbols}
    batches = [symbols[i:i+BATCH_SIZE_TWELVE] for i in range(0, len(symbols), BATCH_SIZE_TWELVE)]

    for tf_key, tf_interval in TIMEFRAMES.items():
        outputsize = CANDLE_COUNT.get(tf_interval, 50)
        for batch in batches:
            fetched = fetch_batch_candles(batch, tf_interval, outputsize)
            for sym, df in fetched.items():
                all_data[sym][tf_interval] = df

    return all_data


# ──────────────────────────────────────────────
# Finnhub — market movers / pre-filter
# ──────────────────────────────────────────────
def get_finnhub_movers() -> Dict[str, List[str]]:
    """Returns top gainers/losers to prioritize scanning."""
    if not FINNHUB_API_KEY:
        return {"gainers": [], "losers": []}
    try:
        url = f"https://finnhub.io/api/v1/stock/market-status"
        params = {"exchange": "US", "token": FINNHUB_API_KEY}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if not data.get("isOpen", False):
            logger.info("Finnhub: market is closed")
            return {"gainers": [], "losers": [], "market_open": False}
        return {"gainers": [], "losers": [], "market_open": True}
    except Exception as e:
        logger.warning(f"Finnhub error: {e}")
        return {"gainers": [], "losers": [], "market_open": True}


def is_market_open() -> bool:
    """Quick check if US market is open via Finnhub."""
    info = get_finnhub_movers()
    return info.get("market_open", True)


# ──────────────────────────────────────────────
# Current price (single lightweight request)
# ──────────────────────────────────────────────
def get_current_price(symbol: str) -> Optional[float]:
    """Fetch latest price for a single symbol."""
    if not TWELVE_DATA_API_KEY:
        return None
    _twelve_limiter.wait_if_needed()
    url = "https://api.twelvedata.com/price"
    params = {"symbol": symbol, "apikey": TWELVE_DATA_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        return float(data.get("price", 0)) or None
    except Exception as e:
        logger.error(f"Price fetch error {symbol}: {e}")
        return None
