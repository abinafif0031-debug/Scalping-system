"""
LIVE DEMO — Single Stock Analysis
Usage: python demo.py AAPL

Shows full pipeline output for one symbol.
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def run_demo(symbol: str = "AAPL"):
    print(f"\n{'='*50}")
    print(f"  SCALPING SYSTEM — LIVE DEMO: {symbol}")
    print(f"{'='*50}\n")

    # 1. Fetch data
    print("📡 Step 1: Fetching multi-timeframe data...")
    from engines.market_data import load_all_timeframes
    tf_data_all = load_all_timeframes([symbol])
    tf_data = tf_data_all.get(symbol, {})

    for tf, df in tf_data.items():
        status = f"{len(df)} candles" if df is not None else "FAILED"
        print(f"   {tf:>6}: {status}")

    # 2. Add indicators
    print("\n📊 Step 2: Computing indicators (5min chart)...")
    from signals.indicators import add_indicators, get_latest_bar_stats
    from config.settings import TIMEFRAMES

    df_5m = tf_data.get(TIMEFRAMES["primary"])
    if df_5m is not None and len(df_5m) > 20:
        df_5m_ind = add_indicators(df_5m)
        stats = get_latest_bar_stats(df_5m_ind)
        if stats:
            print(f"   Close:      ${stats['close']:.4f}")
            print(f"   EMA 9/21:   {'BULL' if stats['ema_bull'] else 'BEAR'}")
            print(f"   RSI:        {stats['rsi']:.1f}")
            print(f"   MACD Bull:  {stats['macd_bull']}")
            print(f"   Above VWAP: {stats['above_vwap']}")
            print(f"   Vol Spike:  {stats['vol_spike']:.2f}x")
            print(f"   ATR:        ${stats['atr']:.4f}")
    else:
        print("   ⚠️  Insufficient data for indicators")

    # 3. Score
    print("\n🧮 Step 3: Scoring signal...")
    from signals.scorer import analyze_symbol, detect_regime
    from signals.indicators import add_indicators as ai2

    df_1h = tf_data.get(TIMEFRAMES["regime"])
    if df_1h is not None:
        df_1h_ind = ai2(df_1h)
        regime = detect_regime(df_1h_ind)
    else:
        regime = "unknown"

    print(f"   Market Regime: {regime.upper()}")

    signal = analyze_symbol(symbol, tf_data)

    if signal is None:
        print(f"\n❌ NO SIGNAL — score below {75} or conflicting timeframes")
    else:
        print(f"\n✅ SIGNAL GENERATED!")
        print(f"   Direction:   {signal.direction}")
        print(f"   Entry:       ${signal.entry_price:.4f}")
        print(f"   Stop Loss:   ${signal.stop_loss:.4f}")
        print(f"   Take Profit: ${signal.take_profit:.4f}")
        print(f"   Confidence:  {signal.confidence:.1f}/100")
        print(f"   Score:       {json.dumps(signal.score.to_dict(), indent=6)}")
        print(f"   Duration:    {signal.trade_duration}")
        print(f"   TF Confirm:  {signal.timeframe_conf}")
        print(f"   Reason:      {signal.reason}")

        # 4. AI Filter
        print("\n🤖 Step 4: AI Filter...")
        from signals.ai_filter import ai_filter_signal
        approved, ai_reason = ai_filter_signal(signal)
        status = "✅ APPROVED" if approved else "❌ REJECTED"
        print(f"   Decision: {status}")
        print(f"   Reason:   {ai_reason}")

        # 5. Telegram preview
        print("\n📩 Step 5: Telegram message preview...")
        from telegram.notifier import send_signal, send_message
        # Print to console instead of sending
        print("   (To send to Telegram, set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        if approved:
            # Only send if tokens are set
            import os
            if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                sent = send_signal(signal, ai_reason)
                print(f"   Telegram: {'Sent ✅' if sent else 'Failed ❌'}")
            else:
                print("   Telegram: Skipped (no credentials)")

    print(f"\n{'='*50}")
    print("  Demo complete!")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    run_demo(symbol)
