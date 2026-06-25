"""
SIGNAL SCORING ENGINE (0–100)
- Trend:      25 pts
- Momentum:   25 pts
- Volume:     25 pts
- Volatility: 25 pts

No trade if score < 75.
Multi-timeframe confluence required.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple
import pandas as pd

from signals.indicators import add_indicators, get_latest_bar_stats
from config.settings import (
    MIN_SCORE_TO_TRADE, SCORE_WEIGHTS,
    HOLD_FAST_MAX, HOLD_SMART_MIN, HOLD_SMART_MAX,
    HOLD_INTRADAY_MIN, HOLD_INTRADAY_MAX,
    TIMEFRAMES
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    trend: float = 0.0
    momentum: float = 0.0
    volume: float = 0.0
    volatility: float = 0.0

    @property
    def total(self) -> float:
        return self.trend + self.momentum + self.volume + self.volatility


@dataclass
class TradeSignal:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    score: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    regime: str = "unknown"
    timeframe_conf: str = ""
    trade_duration: str = ""
    hold_minutes_min: int = 10
    hold_minutes_max: int = 30
    reason: str = ""
    confidence: float = 0.0
    valid: bool = False


# ──────────────────────────────────────────────
# Helpers (SAFE CHECKS)
# ──────────────────────────────────────────────

def safe_df(df: pd.DataFrame, min_len: int = 1):
    return df is not None and isinstance(df, pd.DataFrame) and not df.empty and len(df) >= min_len


def safe_stats(stats: dict):
    return stats is not None and isinstance(stats, dict)


# ──────────────────────────────────────────────
# Regime
# ──────────────────────────────────────────────

def detect_regime(df_1h: pd.DataFrame) -> str:
    if not safe_df(df_1h, 15):
        return "unknown"

    df = add_indicators(df_1h)
    if not safe_df(df, 15):
        return "unknown"

    last = df.iloc[-1]
    prev = df.iloc[-5]

    ema_change_pct = abs(last["ema_fast"] - prev["ema_fast"]) / prev["ema_fast"]

    if ema_change_pct < 0.002:
        return "sideways"

    if last["close"] > last["ema_slow"]:
        return "bullish"
    if last["close"] < last["ema_slow"]:
        return "bearish"

    return "sideways"


# ──────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────

def _score_trend(s5, s15, regime):
    score = 0
    if s5.get("ema_bull"): score += 8
    if s5.get("above_vwap"): score += 7
    if s15.get("ema_bull"): score += 5
    if regime == "bullish": score += 5
    return min(score, 25)


def _score_momentum(s5, s1):
    score = 0
    rsi_5 = s5.get("rsi", 50)
    rsi_1 = s1.get("rsi", 50)

    if 50 < rsi_5 < 70:
        score += 8
    elif 45 < rsi_5 <= 50:
        score += 3

    if s5.get("macd_bull"):
        score += 9
    if rsi_1 > rsi_5:
        score += 4
    if s5.get("ema_cross_up"):
        score += 4

    return min(score, 25)


def _score_volume(s5, s1):
    score = 0
    if s5.get("vol_spike", 1) >= 2:
        score += 15
    elif s5.get("vol_spike", 1) >= 1.5:
        score += 10
    elif s5.get("vol_spike", 1) >= 1.2:
        score += 5

    if s1.get("vol_spike", 1) >= 1.5:
        score += 10

    return min(score, 25)


def _score_volatility(s5):
    atr = s5.get("atr", 0)
    close = s5.get("close", 1)

    if close == 0:
        return 0

    atr_pct = atr / close

    if 0.003 <= atr_pct <= 0.02:
        return 25
    if 0.002 <= atr_pct < 0.003:
        return 12
    if 0.02 < atr_pct <= 0.04:
        return 8

    return 0


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def analyze_symbol(symbol: str, tf_data: Dict[str, pd.DataFrame]) -> Optional[TradeSignal]:

    df_5m = tf_data.get(TIMEFRAMES["primary"])
    df_15m = tf_data.get(TIMEFRAMES["trend"])
    df_1m = tf_data.get(TIMEFRAMES["entry"])
    df_1h = tf_data.get(TIMEFRAMES["regime"])

    if not safe_df(df_5m, 25) or not safe_df(df_15m, 20):
        return None

    df_5m_ind = add_indicators(df_5m)
    df_15m_ind = add_indicators(df_15m)

    df_1m_ind = add_indicators(df_1m) if safe_df(df_1m, 10) else df_5m_ind
    df_1h_ind = add_indicators(df_1h) if safe_df(df_1h, 15) else None

    stats_5m = get_latest_bar_stats(df_5m_ind)
    stats_15m = get_latest_bar_stats(df_15m_ind)
    stats_1m = get_latest_bar_stats(df_1m_ind)

    if not safe_stats(stats_5m) or not safe_stats(stats_15m):
        return None

    regime = detect_regime(df_1h_ind) if df_1h_ind is not None else "unknown"

    if regime == "sideways":
        return None

    if stats_5m.get("ema_bull") != stats_15m.get("ema_bull"):
        return None

    direction = "LONG" if stats_5m.get("ema_bull") else "SHORT"

    score = ScoreBreakdown(
        trend=_score_trend(stats_5m, stats_15m, regime),
        momentum=_score_momentum(stats_5m, stats_1m),
        volume=_score_volume(stats_5m, stats_1m),
        volatility=_score_volatility(stats_5m)
    )

    total = score.total

    if total < 75:
        return None

    entry = stats_5m["close"]
    atr = stats_5m.get("atr", 0)

    sl = entry - atr * 1.5 if direction == "LONG" else entry + atr * 1.5
    tp = entry + atr * 3 if direction == "LONG" else entry - atr * 3

    return TradeSignal(
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        stop_loss=round(sl, 4),
        take_profit=round(tp, 4),
        score=score,
        regime=regime,
        confidence=total,
        valid=True
    )
