"""
MAIN ORCHESTRATOR
- Pre-market: 3 trades max, score >= 88, starts 8:00 AM ET
- Open market: 13 trades max, score >= 78, 9:30 AM–3:30 PM ET
- Batches API calls to stay under rate limits
"""

import logging
import time
from datetime import datetime, time as dtime
import pytz

from config.settings import (
    STOCK_UNIVERSE, SCAN_INTERVAL_SECONDS,
    BATCH_SIZE_TWELVE, TIMEFRAMES,
    MIN_SCORE_PRE_MARKET, MIN_SCORE_OPEN_MARKET,
)
from engines.market_data import load_all_timeframes
from signals.scorer import analyze_symbol
from signals.ai_filter import ai_filter_signal
from risk.manager import RiskManager
from telegram.notifier import (
    send_signal, send_system_status, send_alert,
    send_startup_message, send_market_closed
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/system.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


# ──────────────────────────────────────────────
# Session detection
# ──────────────────────────────────────────────

def get_session() -> str:
    """
    Returns:
        "pre"    → 8:00 AM – 9:29 AM ET
        "open"   → 9:30 AM – 3:30 PM ET
        "closed" → everything else
    """
    now_et = datetime.now(ET).time()
    if dtime(8, 0) <= now_et < dtime(9, 30):
        return "pre"
    if dtime(9, 30) <= now_et <= dtime(15, 30):
        return "open"
    return "closed"


# ──────────────────────────────────────────────
# Main scan
# ──────────────────────────────────────────────

def run_scan(risk_manager: RiskManager, session: str):
    """One full scan of the stock universe."""

    # Min score depends on session
    min_score = MIN_SCORE_PRE_MARKET if session == "pre" else MIN_SCORE_OPEN_MARKET

    can_trade, reason = risk_manager.can_trade(session)
    if not can_trade:
        logger.info(f"Scan skipped — {reason}")
        return

    logger.info(f"[{session.upper()}] Scanning {len(STOCK_UNIVERSE)} symbols | min_score={min_score}")
    signals_sent = 0

    for i in range(0, len(STOCK_UNIVERSE), BATCH_SIZE_TWELVE):
        batch = STOCK_UNIVERSE[i: i + BATCH_SIZE_TWELVE]

        try:
            all_tf_data = load_all_timeframes(batch)
        except Exception as e:
            logger.error(f"Data fetch error for batch {batch}: {e}")
            continue

        for symbol in batch:
            tf_data = all_tf_data.get(symbol, {})

            if not tf_data.get(TIMEFRAMES["primary"]):
                continue

            try:
                signal = analyze_symbol(symbol, tf_data, min_score=min_score)
            except Exception as e:
                logger.error(f"Analysis error {symbol}: {e}")
                continue

            if signal is None:
                continue

            logger.info(f"Signal found: {symbol} {signal.direction} score={signal.confidence:.1f}")

            # AI Filter
            approved, ai_reason = ai_filter_signal(signal)
            if not approved:
                logger.info(f"AI rejected {symbol}: {ai_reason}")
                continue

            # Re-check risk gate before sending
            can_trade, reason = risk_manager.can_trade(session)
            if not can_trade:
                logger.info(f"Risk gate: {reason}")
                break

            # Send to Telegram
            sent = send_signal(signal, ai_reason, session=session)
            if sent:
                risk_manager.register_trade(session)
                signals_sent += 1
                logger.info(f"✅ Signal sent: {symbol} {signal.direction} [{session.upper()}]")

            can_trade, _ = risk_manager.can_trade(session)
            if not can_trade:
                break

        can_trade, _ = risk_manager.can_trade(session)
        if not can_trade:
            break

    logger.info(f"Scan complete — {signals_sent} signals sent [{session.upper()}]")


# ──────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────

def main():
    import os
    os.makedirs("logs", exist_ok=True)

    risk_manager  = RiskManager()
    send_startup_message()
    logger.info("=== Intraday Scalping System STARTED ===")

    last_session = "closed"

    while True:
        try:
            session = get_session()

            if session != "closed":
                # Announce session change
                if session != last_session:
                    label = "🟡 PRE-MARKET" if session == "pre" else "🟢 MARKET OPEN"
                    logger.info(f"{label} — scanning begins")
                    send_alert(f"{label} session started", "INFO")
                    send_system_status(risk_manager.get_status())
                    last_session = session

                run_scan(risk_manager, session)

            else:
                if last_session != "closed":
                    logger.info("Market closed — going to standby")
                    send_market_closed()
                    last_session = "closed"

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
