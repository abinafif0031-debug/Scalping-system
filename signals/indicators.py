"""
TECHNICAL INDICATORS ENGINE
Computes: EMA, VWAP, RSI, MACD, ATR, Volume Spike
Uses pandas-ta for reliability and speed.
"""

import numpy as np
import pandas as pd
import logging
from typing import Optional, Tuple

try:
    import pandas_ta as ta
    USE_PANDAS_TA = True
except ImportError:
    USE_PANDAS_TA = False
    logging.warning("pandas_ta not found, using manual calculations")

from config.settings import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    ATR_PERIOD, VOLUME_MA_LEN
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Core indicator calculations
# ──────────────────────────────────────────────

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    if USE_PANDAS_TA:
        return ta.rsi(close, length=period)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(window=period, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=period, min_periods=1).mean()
    # When loss=0 (pure uptrend), RSI=100; when gain=0 (pure downtrend), RSI=0
    rsi = pd.Series(50.0, index=close.index)
    both_zero = (gain == 0) & (loss == 0)
    pure_up   = (gain > 0) & (loss == 0)
    pure_down = (gain == 0) & (loss > 0)
    normal    = (gain > 0) & (loss > 0)
    rsi[pure_up]   = 100.0
    rsi[pure_down] = 0.0
    rs = gain[normal] / loss[normal]
    rsi[normal] = 100 - (100 / (1 + rs))
    return rsi


def calc_macd(close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)"""
    if USE_PANDAS_TA:
        result = ta.macd(close, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
        if result is not None and not result.empty:
            cols = result.columns.tolist()
            return result[cols[0]], result[cols[2]], result[cols[1]]
    ema_fast   = calc_ema(close, MACD_FAST)
    ema_slow   = calc_ema(close, MACD_SLOW)
    macd_line  = ema_fast - ema_slow
    signal     = calc_ema(macd_line, MACD_SIGNAL)
    histogram  = macd_line - signal
    return macd_line, signal, histogram


def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    if USE_PANDAS_TA:
        result = ta.atr(df["high"], df["low"], df["close"], length=period)
        if result is not None:
            return result
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """Daily VWAP — resets each day."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (tp * df["volume"]).cumsum()
    cum_vol    = df["volume"].cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def calc_volume_spike(volume: pd.Series, ma_len: int = VOLUME_MA_LEN) -> pd.Series:
    """Volume relative to its moving average (ratio). Min periods=5 to avoid NaN early."""
    vol_ma = volume.rolling(ma_len, min_periods=5).mean()
    return volume / vol_ma.replace(0, np.nan).fillna(1.0)


# ──────────────────────────────────────────────
# Full indicator pack for a DataFrame
# ──────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all indicators to df in-place.
    Required columns: open, high, low, close, volume
    """
    if df is None or len(df) < 30:
        return df

    df = df.copy()
    df["ema_fast"]     = calc_ema(df["close"], EMA_FAST)
    df["ema_slow"]     = calc_ema(df["close"], EMA_SLOW)
    df["rsi"]          = calc_rsi(df["close"])
    df["vwap"]         = calc_vwap(df)
    df["atr"]          = calc_atr(df)
    df["vol_spike"]    = calc_volume_spike(df["volume"])

    macd_line, macd_sig, macd_hist = calc_macd(df["close"])
    df["macd"]         = macd_line
    df["macd_signal"]  = macd_sig
    df["macd_hist"]    = macd_hist

    # ema cross direction
    df["ema_bull"]     = df["ema_fast"] > df["ema_slow"]
    df["ema_cross_up"] = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1))

    # price vs vwap
    df["above_vwap"]   = df["close"] > df["vwap"]

    return df


# ──────────────────────────────────────────────
# Latest bar summary
# ──────────────────────────────────────────────

def get_latest_bar_stats(df: pd.DataFrame) -> Optional[dict]:
    """Extract the most recent candle's indicator values."""
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    return {
        "close":       float(last["close"]),
        "ema_fast":    float(last.get("ema_fast", 0)),
        "ema_slow":    float(last.get("ema_slow", 0)),
        "ema_bull":    bool(last.get("ema_bull", False)),
        "ema_cross_up":bool(last.get("ema_cross_up", False)),
        "rsi":         float(last.get("rsi", 50)),
        "macd":        float(last.get("macd", 0)),
        "macd_signal": float(last.get("macd_signal", 0)),
        "macd_hist":   float(last.get("macd_hist", 0)),
        "macd_bull":   float(last.get("macd_hist", 0)) > 0 and float(last.get("macd_hist", 0)) > float(prev.get("macd_hist", 0)),
        "above_vwap":  bool(last.get("above_vwap", False)),
        "vol_spike":   float(last.get("vol_spike", 1.0)),
        "atr":         float(last.get("atr", 0)),
        "volume":      float(last.get("volume", 0)),
    }
