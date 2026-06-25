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

from config.settings import (
    STOCK_UNIVERSE, SCAN_INTERVAL_SECONDS,
    MARKET_OPEN_ET, MARKET_CLOSE_ET, NO_TRADE_AFTER,
    BATCH_SIZE_TWELVE, TIMEFRAMES
)
from engines.market_data import load_all_timeframes, is_market_open
from signals.scorer import analyze_symbol
from signals.ai_filter import ai_filter_signal
from risk.manager import RiskManager
from telegram.notifier import (
    send_signal, send_system_status, send_alert,
    send_startup_message, send_market_closed
)
import os
import logging
import pytz

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

def is_trading_time() -> bool:
    """Check if current ET time is within trading hours."""
    now_et = datetime.now(ET).time()
    open_t  = dtime(9, 30)
    close_t = dtime(15, 30)   # no new trades after 15:30
    return open_t <= now_et <= close_t


def run_scan(risk_manager: RiskManager):
    """One full scan of the stock universe."""
    can_trade, reason = risk_manager.can_trade()
    if not can_trade:
        logger.info(f"Scan skipped — {reason}")
        return

    logger.info(f"Starting scan of {len(STOCK_UNIVERSE)} symbols...")
    signals_sent = 0

    # Process in batches to respect API limits
    for i in range(0, len(STOCK_UNIVERSE), BATCH_SIZE_TWELVE):
        batch = STOCK_UNIVERSE[i : i + BATCH_SIZE_TWELVE]

        # ── Fetch all timeframes for this batch ──
        try:
            all_tf_data = load_all_timeframes(batch)
        except Exception as e:
            logger.error(f"Data fetch error for batch {batch}: {e}")
            continue

        # ── Analyze each symbol ──
        for symbol in batch:
            tf_data = all_tf_data.get(symbol, {})

            # Skip if any critical timeframe missing
            if tf_data.get(TIMEFRAMES["primary"]) is None or tf_data.get(TIMEFRAMES["primary"]).empty:
    return None

            try:
                signal = analyze_symbol(symbol, tf_data)
            except Exception as e:
                logger.error(f"Analysis error {symbol}: {e}")
                continue

            if signal is None:
                continue

            logger.info(f"Signal found: {symbol} {signal.direction} score={signal.confidence:.1f}")

            # ── AI Filter ──
            approved, ai_reason = ai_filter_signal(signal)
            if not approved:
                logger.info(f"AI rejected {symbol}: {ai_reason}")
                send_alert(f"AI rejected {symbol}: {ai_reason}", "INFO")
                continue

            # ── Risk gate (re-check before sending) ──
            can_trade, reason = risk_manager.can_trade()
            if not can_trade:
                logger.info(f"Risk gate: {reason}")
                break

            # ── Send to Telegram ──
            sent = send_signal(signal, ai_reason)
            if sent:
                risk_manager.register_trade()
                signals_sent += 1
                logger.info(f"✅ Signal sent: {symbol} {signal.direction}")

            # Stay under trade limit
            can_trade, _ = risk_manager.can_trade()
            if not can_trade:
                break

        # Check limit between batches too
        can_trade, _ = risk_manager.can_trade()
        if not can_trade:
            break

    logger.info(f"Scan complete — {signals_sent} signals sent")


def main():
    """Main entry point — runs forever."""
    import os
    os.makedirs("logs", exist_ok=True)

    risk_manager = RiskManager()
    send_startup_message()

    logger.info("=== Intraday Scalping System STARTED ===")
    market_was_open = False

    while True:
        try:
            if is_trading_time():
                if not market_was_open:
                    logger.info("Market open — scanning begins")
                    market_was_open = True
                    status = risk_manager.get_status()
                    send_system_status(status)

                run_scan(risk_manager)

            else:
                if market_was_open:
                    logger.info("Market closed — going to standby")
                    market_was_open = False
                    send_market_closed()

            time.sleep(SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("System stopped by user")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            send_alert(f"Main loop error: {e}", "ERROR")
            time.sleep(30)


if __name__ == "__main__":
    main()
