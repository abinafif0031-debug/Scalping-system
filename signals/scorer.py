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
from engines.market_data import get_current_price

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    trend:      float = 0.0
    momentum:   float = 0.0
    volume:     float = 0.0
    volatility: float = 0.0

    @property
    def total(self) -> float:
        return self.trend + self.momentum + self.volume + self.volatility

    def to_dict(self) -> dict:
        return {
            "trend":      round(self.trend, 1),
            "momentum":   round(self.momentum, 1),
            "volume":     round(self.volume, 1),
            "volatility": round(self.volatility, 1),
            "total":      round(self.total, 1),
        }


@dataclass
class TradeSignal:
    symbol:          str
    direction:       str           # "LONG" | "SHORT"
    entry_price:     float
    stop_loss:       float
    take_profit:     float
    score:           ScoreBreakdown = field(default_factory=ScoreBreakdown)
    regime:          str = "unknown"
    timeframe_conf:  str = ""
    trade_duration:  str = ""
    hold_minutes_min: int = 10
    hold_minutes_max: int = 30
    reason:          str = ""
    confidence:      float = 0.0
    valid:           bool = False

    def to_dict(self) -> dict:
        return {
            "symbol":          self.symbol,
            "direction":       self.direction,
            "entry_price":     round(self.entry_price, 4),
            "stop_loss":       round(self.stop_loss, 4),
            "take_profit":     round(self.take_profit, 4),
            "confidence":      round(self.confidence, 1),
            "score":           self.score.to_dict(),
            "regime":          self.regime,
            "timeframe_conf":  self.timeframe_conf,
            "trade_duration":  self.trade_duration,
            "hold_minutes":    f"{self.hold_minutes_min}–{self.hold_minutes_max}",
            "reason":          self.reason,
        }


# ──────────────────────────────────────────────
# Market Regime Detection (1H chart)
# ──────────────────────────────────────────────

def detect_regime(df_1h: pd.DataFrame) -> str:
    """
    bullish | bearish | sideways
    Based on EMA slope and price structure on 1H.
    """
    if df_1h is None or len(df_1h) < 15:
        return "unknown"
    df = add_indicators(df_1h)
    last = df.iloc[-1]
    prev = df.iloc[-min(5, len(df)-1)]  # 5 bars ago

    ema_trend_up   = float(last["ema_fast"]) > float(prev["ema_fast"])
    ema_trend_down = float(last["ema_fast"]) < float(prev["ema_fast"])
    price_vs_ema   = float(last["close"]) > float(last["ema_slow"])

    # Sideways: EMA essentially flat (< 0.5% change over 5 bars)
    ema_change_pct = abs(float(last["ema_fast"]) - float(prev["ema_fast"])) / float(prev["ema_fast"])
    if ema_change_pct < 0.002:   # < 0.2% EMA movement = sideways
        return "sideways"

    if ema_trend_up and price_vs_ema:
        return "bullish"
    if ema_trend_down and not price_vs_ema:
        return "bearish"
    return "sideways"


# ──────────────────────────────────────────────
# Individual score components
# ──────────────────────────────────────────────

def _score_trend(stats_5m: dict, stats_15m: dict, regime: str) -> float:
    """Max 25 pts"""
    score = 0.0
    if stats_5m.get("ema_bull"):    score += 8
    if stats_5m.get("above_vwap"): score += 7
    if stats_15m.get("ema_bull"):   score += 5
    if regime == "bullish":         score += 5
    return min(score, 25.0)


def _score_momentum(stats_5m: dict, stats_1m: dict) -> float:
    """Max 25 pts"""
    score = 0.0
    rsi_5m = stats_5m.get("rsi", 50)
    rsi_1m = stats_1m.get("rsi", 50)

    # RSI momentum: 50–70 bullish zone (not overbought)
    if 50 < rsi_5m < 70:            score += 8
    elif 45 < rsi_5m <= 50:         score += 3   # borderline

    # MACD confirmation
    if stats_5m.get("macd_bull"):   score += 9
    if rsi_1m > rsi_5m:             score += 4   # momentum strengthening
    if stats_5m.get("ema_cross_up"): score += 4

    return min(score, 25.0)


def _score_volume(stats_5m: dict, stats_1m: dict) -> float:
    """Max 25 pts"""
    score = 0.0
    vol_spike = stats_5m.get("vol_spike", 1.0)
    vol_1m    = stats_1m.get("vol_spike", 1.0)

    if vol_spike >= 2.0:   score += 15
    elif vol_spike >= 1.5: score += 10
    elif vol_spike >= 1.2: score += 5

    if vol_1m >= 1.5:      score += 10

    return min(score, 25.0)


def _score_volatility(stats_5m: dict, entry: float) -> float:
    """Max 25 pts — ATR within reasonable bounds"""
    score = 0.0
    atr   = stats_5m.get("atr", 0)
    close = stats_5m.get("close", 1)

    if close == 0:
        return 0.0

    atr_pct = atr / close
    # Ideal ATR: 0.3%–2% of price (tradeable range)
    if 0.003 <= atr_pct <= 0.02:  score += 20
    elif 0.002 <= atr_pct < 0.003: score += 12
    elif 0.02 < atr_pct <= 0.04:  score += 8

    # Bonus: clean price structure (close near high of bar)
    return min(score + 5, 25.0) if score > 0 else 0.0


# ──────────────────────────────────────────────
# SL/TP calculation
# ──────────────────────────────────────────────

def calc_sl_tp(
    entry: float,
    atr: float,
    direction: str,
    r_ratio: float = 2.0
) -> Tuple[float, float]:
    """ATR-based SL, with R:R take profit."""
    sl_distance = atr * 1.5
    if direction == "LONG":
        sl = entry - sl_distance
        tp = entry + (sl_distance * r_ratio)
    else:
        sl = entry + sl_distance
        tp = entry - (sl_distance * r_ratio)
    return round(sl, 4), round(tp, 4)


# ──────────────────────────────────────────────
# Trade duration selector
# ──────────────────────────────────────────────

def select_trade_duration(score: float, macd_hist_increasing: bool) -> Tuple[str, int, int]:
    """
    Returns (label, min_minutes, max_minutes)
    """
    if score >= 92 and macd_hist_increasing:
        return "⚡ Fast Scalp", HOLD_FAST_MAX // 2, HOLD_FAST_MAX
    elif score >= 82:
        return "🧠 Smart Scalp", HOLD_SMART_MIN, HOLD_SMART_MAX
    else:
        return "📈 Intraday Hold", HOLD_INTRADAY_MIN, HOLD_INTRADAY_MAX


# ──────────────────────────────────────────────
# MAIN: analyze a single symbol
# ──────────────────────────────────────────────

def analyze_symbol(
    symbol: str,
    tf_data: Dict[str, pd.DataFrame]
) -> Optional[TradeSignal]:
    """
    Returns a TradeSignal if score >= 75, else None.

    tf_data keys: "1min", "5min", "15min", "1h"
    """
    df_1m  = tf_data.get(TIMEFRAMES["entry"])
    df_5m  = tf_data.get(TIMEFRAMES["primary"])
    df_15m = tf_data.get(TIMEFRAMES["trend"])
    df_1h  = tf_data.get(TIMEFRAMES["regime"])

    # Need at least 5m and 15m
    if df_5m is None or len(df_5m) < 25:
        return None
    if df_15m is None or len(df_15m) < 20:
        return None

    # Add indicators to all timeframes
    df_5m_ind  = add_indicators(df_5m)
    df_15m_ind = add_indicators(df_15m)
    df_1m_ind  = add_indicators(df_1m) if df_1m is not None and len(df_1m) > 10 else None
    df_1h_ind  = add_indicators(df_1h) if df_1h is not None and len(df_1h) > 15 else None

    stats_5m  = get_latest_bar_stats(df_5m_ind)
    stats_15m = get_latest_bar_stats(df_15m_ind)
    stats_1m  = get_latest_bar_stats(df_1m_ind) if df_1m_ind is not None else stats_5m

    if not stats_5m or not stats_15m:
        return None

    # Regime
    regime = detect_regime(df_1h_ind) if df_1h_ind is not None else "unknown"

    # ❌ No trade in sideways market
    if regime == "sideways":
        return None

    # ❌ 15m must confirm 5m direction
    if stats_5m.get("ema_bull") != stats_15m.get("ema_bull"):
        return None  # conflicting timeframes

    # Determine direction
    direction = "LONG" if stats_5m.get("ema_bull") else "SHORT"

    # Score components
    breakdown = ScoreBreakdown(
        trend      = _score_trend(stats_5m, stats_15m, regime),
        momentum   = _score_momentum(stats_5m, stats_1m),
        volume     = _score_volume(stats_5m, stats_1m),
        volatility = _score_volatility(stats_5m, stats_5m["close"]),
    )

    if breakdown.total < MIN_SCORE_TO_TRADE:
        return None

    from engines.market_data import get_current_price
live_price = get_current_price(symbol)
entry = live_price if live_price else stats_5m["close"]

    atr   = stats_5m["atr"]
    sl, tp = calc_sl_tp(entry, atr, direction, r_ratio=2.0)

    macd_increasing = float(df_5m_ind.iloc[-1].get("macd_hist", 0)) > float(df_5m_ind.iloc[-2].get("macd_hist", 0))
    duration_label, hold_min, hold_max = select_trade_duration(breakdown.total, macd_increasing)

    # Timeframe confirmation string
    tf_parts = []
    if stats_15m.get("ema_bull") == stats_5m.get("ema_bull"):
        tf_parts.append("15m✅")
    if regime in ("bullish", "bearish"):
        tf_parts.append(f"1h:{regime}✅")
    if stats_1m.get("ema_bull") == stats_5m.get("ema_bull"):
        tf_parts.append("1m✅")
    tf_conf = " | ".join(tf_parts)

    # Reason summary
    reasons = []
    if stats_5m.get("ema_cross_up"): reasons.append("EMA cross")
    if stats_5m.get("above_vwap"):   reasons.append("above VWAP")
    if stats_5m.get("macd_bull"):    reasons.append("MACD bullish")
    if stats_5m.get("vol_spike", 1) >= 1.5: reasons.append(f"vol spike x{stats_5m['vol_spike']:.1f}")
    reason = " + ".join(reasons) if reasons else "Multi-indicator confluence"

    signal = TradeSignal(
        symbol          = symbol,
        direction       = direction,
        entry_price     = entry,
        stop_loss       = sl,
        take_profit     = tp,
        score           = breakdown,
        regime          = regime,
        timeframe_conf  = tf_conf,
        trade_duration  = duration_label,
        hold_minutes_min= hold_min,
        hold_minutes_max= hold_max,
        reason          = reason,
        confidence      = breakdown.total,
        valid           = True,
    )
    return signal
