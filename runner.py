"""
BACKTEST MODULE
Simulates the signal engine on historical data.
Reports: win rate, drawdown, avg R:R, equity curve.
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

from engines.market_data import fetch_batch_candles
from signals.scorer import analyze_symbol
from config.settings import (
    TIMEFRAMES, CANDLE_COUNT, BACKTEST_DIR,
    MAX_DAILY_LOSS_PCT, MAX_CONSECUTIVE_LOSSES
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Backtest result
# ──────────────────────────────────────────────

class BacktestResult:
    def __init__(self):
        self.trades: List[dict] = []

    def add_trade(self, trade: dict):
        self.trades.append(trade)

    def summary(self) -> dict:
        if not self.trades:
            return {"error": "No trades in backtest"}

        wins  = [t for t in self.trades if t["pnl_r"] > 0]
        loss  = [t for t in self.trades if t["pnl_r"] <= 0]
        total = len(self.trades)

        win_rate = len(wins) / total if total else 0
        avg_win  = np.mean([t["pnl_r"] for t in wins])  if wins else 0
        avg_loss = np.mean([t["pnl_r"] for t in loss])  if loss else 0
        avg_rr   = abs(avg_win / avg_loss) if avg_loss else float("inf")

        # Equity curve
        equity = [1.0]
        for t in self.trades:
            equity.append(equity[-1] * (1 + t["pnl_pct"]))
        equity_arr = np.array(equity)

        # Max drawdown
        peak     = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - peak) / peak
        max_dd   = float(drawdown.min())

        return {
            "total_trades":   total,
            "wins":           len(wins),
            "losses":         len(loss),
            "win_rate":       f"{win_rate:.1%}",
            "avg_win_r":      f"{avg_win:.2f}R",
            "avg_loss_r":     f"{avg_loss:.2f}R",
            "avg_rr_ratio":   f"{avg_rr:.2f}",
            "max_drawdown":   f"{max_dd:.1%}",
            "final_equity":   f"{equity_arr[-1]:.3f}x",
            "total_return":   f"{(equity_arr[-1] - 1):.1%}",
        }

    def to_csv(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(self.trades).to_csv(path, index=False)
        logger.info(f"Backtest saved: {path}")


# ──────────────────────────────────────────────
# Simulate a single trade
# ──────────────────────────────────────────────

def simulate_trade(
    signal_dict: dict,
    future_candles: pd.DataFrame
) -> Optional[dict]:
    """
    Walk forward through future_candles to find SL or TP hit.
    Returns trade result dict.
    """
    entry = signal_dict["entry_price"]
    sl    = signal_dict["stop_loss"]
    tp    = signal_dict["take_profit"]
    sym   = signal_dict["symbol"]
    direction = signal_dict["direction"]

    risk   = abs(entry - sl)
    reward = abs(tp - entry)
    rr     = reward / risk if risk else 0

    for _, candle in future_candles.iterrows():
        high = candle["high"]
        low  = candle["low"]

        if direction == "LONG":
            if low  <= sl: return _trade_result(sym, entry, sl, sl, direction, signal_dict["confidence"], rr)
            if high >= tp: return _trade_result(sym, entry, tp, tp, direction, signal_dict["confidence"], rr)
        else:
            if high >= sl: return _trade_result(sym, entry, sl, sl, direction, signal_dict["confidence"], rr)
            if low  <= tp: return _trade_result(sym, entry, tp, tp, direction, signal_dict["confidence"], rr)

    # Time-based exit at last candle
    exit_price = float(future_candles.iloc[-1]["close"])
    return _trade_result(sym, entry, exit_price, tp, direction, signal_dict["confidence"], rr)


def _trade_result(symbol, entry, exit_price, tp, direction, score, rr) -> dict:
    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry
    else:
        pnl_pct = (entry - exit_price) / entry

    pnl_r = pnl_pct / (abs(entry - tp) / abs(rr)) if rr else pnl_pct * 100
    return {
        "symbol":     symbol,
        "entry":      entry,
        "exit":       exit_price,
        "direction":  direction,
        "pnl_pct":    pnl_pct,
        "pnl_r":      pnl_pct / (1 / rr) if rr else pnl_pct,
        "score":      score,
        "win":        pnl_pct > 0,
    }


# ──────────────────────────────────────────────
# Run backtest on a single symbol
# ──────────────────────────────────────────────

def backtest_symbol(symbol: str, outputsize: int = 200) -> BacktestResult:
    """
    Fetch historical data and run signal engine over rolling windows.
    """
    result = BacktestResult()
    logger.info(f"Backtesting {symbol}...")

    # Fetch data
    tf_data: Dict[str, pd.DataFrame] = {}
    for tf_key, interval in TIMEFRAMES.items():
        batch = fetch_batch_candles([symbol], interval, outputsize)
        if symbol in batch:
            tf_data[interval] = batch[symbol]

    df_5m = tf_data.get(TIMEFRAMES["primary"])
    if df_5m is None or len(df_5m) < 60:
        logger.warning(f"{symbol}: insufficient 5m data")
        return result

    # Rolling window: analyze at each bar
    window_size = 50
    for i in range(window_size, len(df_5m) - 10):
        window_tf = {}
        for tf_key, interval in TIMEFRAMES.items():
            df = tf_data.get(interval)
            if df is not None:
                # Scale window by timeframe ratio
                ratio = {"1min": 5, "5min": 1, "15min": 1, "1h": 1}.get(interval, 1)
                end_idx = min(i * ratio, len(df))
                start_idx = max(0, end_idx - window_size)
                window_tf[interval] = df.iloc[start_idx:end_idx].copy()

        signal = analyze_symbol(symbol, window_tf)
        if signal is None:
            continue

        # Future 10 candles for simulation
        future = df_5m.iloc[i:i+10]
        trade  = simulate_trade(signal.to_dict(), future)
        if trade:
            result.add_trade(trade)

    return result


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    result = backtest_symbol(symbol, outputsize=300)
    summary = result.summary()

    print(f"\n{'='*40}")
    print(f"BACKTEST RESULTS: {symbol}")
    print(f"{'='*40}")
    for k, v in summary.items():
        print(f"  {k:<20}: {v}")
    print(f"{'='*40}\n")

    os.makedirs(BACKTEST_DIR, exist_ok=True)
    result.to_csv(f"{BACKTEST_DIR}/{symbol}_backtest.csv")
