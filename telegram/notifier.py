"""
TELEGRAM BOT — Signal Notifications
Sends formatted trade signals to a Telegram chat.
"""

import logging
import requests
from datetime import datetime

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from signals.scorer import TradeSignal

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send any message to the configured chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured")
        print(f"[TELEGRAM] {text}")
        return False
    try:
        resp = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def send_signal(signal: TradeSignal, ai_reason: str = "", session: str = "open") -> bool:
    """Format and send a trade signal."""
    direction_emoji = "🟢 LONG" if signal.direction == "LONG" else "🔴 SHORT"
    regime_emoji    = {"bullish": "📈", "bearish": "📉", "sideways": "➡️"}.get(signal.regime, "❓")
    session_label   = "🌅 PRE-MARKET" if session == "pre" else "🟢 OPEN MARKET"

    score_bar = _make_score_bar(signal.confidence)

    msg = f"""
⚡ <b>TRADE SIGNAL</b> ⚡ [{session_label}]
━━━━━━━━━━━━━━━━━━━━
📌 <b>{signal.symbol}</b> — {direction_emoji}

💰 <b>Entry:</b>  ${signal.entry_price:,.4f}
🛑 <b>Stop Loss:</b>  ${signal.stop_loss:,.4f}
🎯 <b>Take Profit:</b>  ${signal.take_profit:,.4f}

📊 <b>Confidence:</b> {signal.confidence:.1f}/100
{score_bar}
  Trend:      {signal.score.trend:.0f}/25
  Momentum:   {signal.score.momentum:.0f}/25
  Volume:     {signal.score.volume:.0f}/25
  Volatility: {signal.score.volatility:.0f}/25

{regime_emoji} <b>Market Regime:</b> {signal.regime.upper()}
⏱ <b>Timeframes:</b> {signal.timeframe_conf}
⏳ <b>Duration:</b> {signal.trade_duration} ({signal.hold_minutes_min}–{signal.hold_minutes_max} min)

💡 <b>Reason:</b> {signal.reason}
{f'🤖 <b>AI:</b> {ai_reason}' if ai_reason else ''}

⚠️ <i>SIGNALS ONLY — Not financial advice</i>
🕐 {datetime.now().strftime('%H:%M:%S ET')}
""".strip()

    return send_message(msg)


def send_system_status(status: dict) -> bool:
    """Send daily risk status update."""
    allowed = "✅ Active" if status["trading_allowed"] else f"⛔ Halted: {status['halt_reason']}"
    msg = f"""
📊 <b>SYSTEM STATUS</b>
━━━━━━━━━━━━━━━━━━━━
📅 Date: {status['date']}
🌅 Pre-market trades: {status.get('pre_market_trades', '0/0')}
🟢 Open-market trades: {status.get('open_market_trades', '0/0')}
📈 Daily PnL: {status['daily_pnl_pct']}
❌ Consec. Losses: {status['consecutive_losses']}
🔒 Status: {allowed}
""".strip()
    return send_message(msg)


def send_alert(message: str, level: str = "INFO") -> bool:
    emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🚨"}.get(level, "📢")
    return send_message(f"{emoji} <b>{level}</b>\n{message}")


def send_startup_message() -> bool:
    return send_message(
        "🚀 <b>Scalping System ONLINE</b>\n"
        "Pre-market scanning from 8:00 AM ET (max 3 trades, score ≥88).\n"
        "Open-market scanning from 9:30 AM ET (max 13 trades, score ≥78)."
    )


def send_market_closed() -> bool:
    return send_message("🔒 <b>Market closed</b> — System on standby until next session.")


def _make_score_bar(score: float, width: int = 10) -> str:
    filled = int((score / 100) * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:.0f}%"
