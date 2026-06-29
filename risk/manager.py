"""
RISK MANAGEMENT ENGINE (FIXED & STABLE)
- Daily loss limit tracker
- Max trades per day
- Session-based tracking (pre/open)
- Consecutive loss guard
- Position sizing
- State persistence (safe)
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Tuple
from datetime import date

from config.settings import (
    MAX_DAILY_LOSS_PCT,
    MAX_TRADES_PER_DAY,
    MAX_CONSECUTIVE_LOSSES,
    RISK_PER_TRADE_PCT,
    STATE_FILE
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────

@dataclass
class DailyState:
    date: str = ""

    # trades
    trades_taken: int = 0
    pre_market_trades: int = 0
    open_market_trades: int = 0

    # performance
    daily_pnl_pct: float = 0.0
    consecutive_losses: int = 0

    # control
    trading_halted: bool = False
    halt_reason: str = ""

    def reset_if_new_day(self):
        today = str(date.today())

        if self.date != today:
            self.date = today
            self.trades_taken = 0
            self.pre_market_trades = 0
            self.open_market_trades = 0
            self.daily_pnl_pct = 0.0
            self.consecutive_losses = 0
            self.trading_halted = False
            self.halt_reason = ""

            logger.info(f"New trading day: {today} — state reset")


# ──────────────────────────────────────────────
# RISK MANAGER
# ──────────────────────────────────────────────

class RiskManager:

    def __init__(self):
        self.state = DailyState()
        self._load_state()
        self.state.reset_if_new_day()

    # ──────────────────────────────
    # LOAD / SAVE
    # ──────────────────────────────

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self.state = DailyState(**data)
        except Exception as e:
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(asdict(self.state), f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state: {e}")

    # ──────────────────────────────
    # TRADE CHECK
    # ──────────────────────────────

    def can_trade(self) -> Tuple[bool, str]:
        self.state.reset_if_new_day()

        if self.state.trading_halted:
            return False, f"Trading halted: {self.state.halt_reason}"

        if self.state.trades_taken >= MAX_TRADES_PER_DAY:
            return False, "Max trades reached"

        if self.state.daily_pnl_pct <= -MAX_DAILY_LOSS_PCT:
            self._halt("Daily loss limit hit")
            return False, self.state.halt_reason

        if self.state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            self._halt("Consecutive losses limit hit")
            return False, self.state.halt_reason

        return True, "OK"

    def _halt(self, reason: str):
        self.state.trading_halted = True
        self.state.halt_reason = reason
        self._save_state()
        logger.warning(f"⛔ Trading HALTED: {reason}")

    # ──────────────────────────────
    # TRADE TRACKING
    # ──────────────────────────────

    def register_trade(self, session: str = "open"):
        self.state.trades_taken += 1

        if session == "pre":
            self.state.pre_market_trades += 1
        else:
            self.state.open_market_trades += 1

        self._save_state()

    def register_result(self, pnl_pct: float, won: bool):
        self.state.daily_pnl_pct += pnl_pct

        if won:
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1

        self._save_state()

        logger.info(
            f"Trade result: {'WIN' if won else 'LOSS'} | "
            f"PnL: {pnl_pct:.2%} | "
            f"Daily: {self.state.daily_pnl_pct:.2%}"
        )

    # ──────────────────────────────
    # POSITION SIZING
    # ──────────────────────────────

    def calc_position_size(self, account_value: float, entry: float, stop_loss: float) -> float:
        risk_amount = account_value * RISK_PER_TRADE_PCT
        sl_distance = abs(entry - stop_loss)

        if sl_distance == 0:
            return 0.0

        return round(risk_amount / sl_distance, 2)

    # ──────────────────────────────
    # STATUS
    # ──────────────────────────────

   def get_status(self) -> dict:
    self.state.reset_if_new_day()

    return {
        "date": self.state.date,
        "trades_taken": self.state.trades_taken,
        "pre_market_trades": self.state.pre_market_trades,
        "open_market_trades": self.state.open_market_trades,
        "trades_remaining": MAX_TRADES_PER_DAY - self.state.trades_taken,
        "daily_pnl_pct": f"{self.state.daily_pnl_pct:.2%}",
        "consecutive_losses": self.state.consecutive_losses,

        # 🔥 FIX REQUIRED KEYS (for notifier)
        "trading_allowed": not self.state.trading_halted,
        "halt_reason": self.state.halt_reason,

        # optional safety
        "trading_halted": self.state.trading_halted,
    }
