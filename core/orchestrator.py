"""
MAIN ORCHESTRATOR
- Scans stock universe every 2 minutes
- Batches API calls to stay under rate limits
- Applies full pipeline: data → indicators → score → AI filter → telegram
"""

import logging
import time
from datetime import datetime, time as dtime
import pytz
import os

from config.settings import (
    STOCK_UNIVERSE, SCAN_INTERVAL_SECONDS,
    TIMEFRAMES
)
from engines.market_data import load_all_timeframes
from signals.scorer import analyze_symbol
from signals.ai_filter import ai_filter_signal
from risk.manager import RiskManager
from telegram.notifier import (
    send_signal, send_system_status,
    send_alert, send_startup_message,
    send_market_closed
)

# ─────────────────────────────
# LOGGING (FIXED)
# ─────────────────────────────

BASE_DIR = "/app"
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "system.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode="a"),
    ],
)

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


# ─────────────────────────────
# TRADING TIME (UPDATED ✅ PRE + REG + AFTER)
# ─────────────────────────────

def is_trading_time() -> bool:
    now_et = datetime.now(ET).time()

    pre_market_start = dtime(4, 0)
    market_close     = dtime(20, 0)

    return pre_market_start <= now_et <= market_close
def get_session() -> str:
    """Returns: 'pre', 'open', or 'closed'"""
    now_et = datetime.now(ET).time()
    if dtime(8, 0) <= now_et < dtime(9, 30):
        return "pre"
    if dtime(9, 30) <= now_et <= dtime(15, 30):
        return "open"
    return "closed"

# ─────────────────────────────
# SCAN ENGINE
# ─────────────────────────────

def run_scan(risk_manager: RiskManager):

    can_trade, reason = risk_manager.can_trade()
    if not can_trade:
        logger.info(f"Scan skipped — {reason}")
        return

    logger.info(f"Starting scan of {len(STOCK_UNIVERSE)} symbols...")
    signals_sent = 0

    for i in range(0, len(STOCK_UNIVERSE), 10):
        batch = STOCK_UNIVERSE[i:i + 10]

        try:
            all_tf_data = load_all_timeframes(batch)
        except Exception as e:
            logger.error(f"Data fetch error: {e}")
            continue

        for symbol in batch:
            tf_data = all_tf_data.get(symbol, {})

            primary_df = tf_data.get(TIMEFRAMES["primary"])
            if primary_df is None or getattr(primary_df, "empty", True):
                continue

            try:
                signal = analyze_symbol(symbol, tf_data)
            except Exception as e:
                logger.error(f"Analysis error {symbol}: {e}")
                continue

            if signal is None:
                continue

            logger.info(f"Signal: {symbol} {signal.direction} score={signal.confidence:.1f}")

            approved, ai_reason = ai_filter_signal(signal)
            if not approved:
                logger.info(f"AI rejected {symbol}")
                continue

            can_trade, reason = risk_manager.can_trade()
            if not can_trade:
                break

            if send_signal(signal, ai_reason):
                risk_manager.register_trade()
                signals_sent += 1

            can_trade, _ = risk_manager.can_trade()
            if not can_trade:
                break

    logger.info(f"Scan complete — {signals_sent} signals sent")


# ─────────────────────────────
# MAIN LOOP
# ─────────────────────────────

def main():

    os.makedirs("/app/logs", exist_ok=True)

    risk_manager = RiskManager()
    send_startup_message()

    logger.info("=== Intraday Scalping System STARTED ===")

    market_was_open = False

    while True:
        try:
            if is_trading_time():

                if not market_was_open:
                    logger.info("Market session started (PRE/REG/AFTER)")
                    market_was_open = True
                    send_system_status(risk_manager.get_status())

                run_scan(risk_manager)

            else:
                if market_was_open:
                    logger.info("Market closed")
                    market_was_open = False
                    send_market_closed()

            time.sleep(SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break

        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            send_alert(f"Main loop error: {e}", "ERROR")
            time.sleep(30)


if __name__ == "__main__":
    main()
