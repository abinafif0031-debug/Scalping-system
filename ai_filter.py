"""
AI FILTER — Claude API
Role: APPROVE / REJECT signal only.
Does NOT generate signals from scratch.
"""

import json
import logging
import requests
from typing import Optional

from config.settings import ANTHROPIC_API_KEY
from signals.scorer import TradeSignal

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


def ai_filter_signal(signal: TradeSignal) -> tuple[bool, str]:
    """
    Ask Claude to APPROVE or REJECT the signal.
    Returns (approved: bool, reason: str)
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping AI filter, auto-approve")
        return True, "AI filter skipped (no API key)"

    prompt = f"""You are a strict risk-management AI for an institutional scalping system.
Review this trade signal and output ONLY a JSON object.

SIGNAL:
- Symbol: {signal.symbol}
- Direction: {signal.direction}
- Entry: ${signal.entry_price}
- Stop Loss: ${signal.stop_loss}
- Take Profit: ${signal.take_profit}
- Score: {signal.confidence:.1f}/100
  - Trend: {signal.score.trend}/25
  - Momentum: {signal.score.momentum}/25
  - Volume: {signal.score.volume}/25
  - Volatility: {signal.score.volatility}/25
- Market Regime: {signal.regime}
- Timeframe Confirmation: {signal.timeframe_conf}
- Reason: {signal.reason}
- Hold Duration: {signal.trade_duration}

Your job: Check for logical errors only. Reject if:
1. SL/TP ratio is illogical (TP closer than SL)
2. Signal contradicts stated regime (e.g., LONG in bearish regime)
3. Score components don't match the reason
4. Any obvious risk management violation

Output ONLY this JSON:
{{"decision": "APPROVE" or "REJECT", "reason": "one sentence"}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      CLAUDE_MODEL,
                "max_tokens": 200,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()

        # Parse JSON response
        text_clean = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text_clean)
        approved = result.get("decision", "REJECT").upper() == "APPROVE"
        reason   = result.get("reason", "No reason provided")
        return approved, reason

    except json.JSONDecodeError as e:
        logger.error(f"AI filter JSON parse error: {e} | text={text}")
        return True, "AI parse error — auto approved"
    except Exception as e:
        logger.error(f"AI filter error: {e}")
        return True, f"AI filter failed ({type(e).__name__}) — auto approved"
