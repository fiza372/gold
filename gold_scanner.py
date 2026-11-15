import os
import sys
import time
import requests
from datetime import datetime
import pandas as pd
import yfinance as yf

def send_telegram(msg):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Note: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is missing from secrets.")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.post(url, json=payload, headers=headers, timeout=12)
        if r.status_code == 200:
            print("✅ Telegram notification sent successfully!")
            return True
        else:
            print(f"❌ Telegram API returned status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print("❌ Telegram request failed:", e)
        return False

def analyze_gold():
    symbol = "GC=F" # Gold Futures (tracks spot Gold XAU/USD)
    print(f"==================================================")
    print(f"📊 Gold (XAU/USD) Cloud Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"==================================================")

    # If triggered manually or SEND_TEST is true, send an instant confirmation ping!
    is_test = os.environ.get("SEND_TEST", "").lower() in ["true", "1", "yes"] or "--test" in sys.argv
    if is_test:
        print("Sending manual test confirmation to Telegram...")
        test_msg = (
            "🔔 *Gold Cloud Scanner is LIVE!* 🚀\n\n"
            "✅ Your 24/7 cloud automation is working perfectly!\n"
            "📅 *Market Notice:* Gold trades Mon-Fri. Whenever a valid 1H/15M setup triggers, you will receive exact Entry, Stop Loss, and Take Profit here."
        )
        send_telegram(test_msg)
    
    # 1. Fetch 1-Hour data for macro trend
    print("Fetching 1-Hour data...")
    df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
    if df_1h.empty:
        df_1h = yf.download("XAUUSD=X", period="5d", interval="1h", progress=False)
        if df_1h.empty:
            print("Market data unavailable currently.")
            return
    
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [col[0] for col in df_1h.columns]

    df_1h['EMA_20'] = df_1h['Close'].ewm(span=20, adjust=False).mean()
    df_1h['EMA_50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    
    last_1h = df_1h.iloc[-1]
    
    htf_bullish = bool(last_1h['Close'] > last_1h['EMA_20'] and last_1h['EMA_20'] >= last_1h['EMA_50'])
    htf_bearish = bool(last_1h['Close'] < last_1h['EMA_20'] and last_1h['EMA_20'] <= last_1h['EMA_50'])
    htf_bias = "BULLISH 🟢" if htf_bullish else ("BEARISH 🔴" if htf_bearish else "NEUTRAL / CHOP ⚪")
    
    print(f"1-Hour Trend Bias: {htf_bias} (Close: {last_1h['Close']:.2f})")
    
    # 2. Fetch 15-Minute data for execution & sweeps
    print("Fetching 15-Minute data...")
    df_15m = yf.download(symbol, period="5d", interval="15m", progress=False)
    if df_15m.empty:
        df_15m = yf.download("XAUUSD=X", period="5d", interval="15m", progress=False)
        if df_15m.empty:
            print("15M data unavailable.")
            return

    if isinstance(df_15m.columns, pd.MultiIndex):
        df_15m.columns = [col[0] for col in df_15m.columns]

    df_15m['EMA_20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
    df_15m['EMA_50'] = df_15m['Close'].ewm(span=50, adjust=False).mean()

    last_15m = df_15m.iloc[-1]
    current_price = float(last_15m['Close'])
    
    ltf_bullish = bool(last_15m['Close'] > last_15m['EMA_20'] and last_15m['EMA_20'] >= last_15m['EMA_50'])
    ltf_bearish = bool(last_15m['Close'] < last_15m['EMA_20'] and last_15m['EMA_20'] <= last_15m['EMA_50'])
    ltf_bias = "BULLISH 🟢" if ltf_bullish else ("BEARISH 🔴" if ltf_bearish else "NEUTRAL / CHOP ⚪")
    
    print(f"15-Minute Trend Bias: {ltf_bias} (Close: {current_price:.2f})")
    
    # 3. Alignment Check
    aligned_bullish = htf_bullish and ltf_bullish
    aligned_bearish = htf_bearish and ltf_bearish
    
    print("\n---------------- STEP 1: ALIGNMENT ----------------")
    if aligned_bullish:
        print("✅ ALIGNED: Both 1H and 15M are Bullish -> ONLY Longs.")
    elif aligned_bearish:
        print("✅ ALIGNED: Both 1H and 15M are Bearish -> ONLY Shorts.")
    else:
        print("⏳ MISALIGNED: 1H and 15M do not agree. No trade.")

    # 4. Swings and Liquidity Levels on 15M
    highs = df_15m['High'].values
    lows = df_15m['Low'].values
    swing_highs = []
    swing_lows = []
    k = 4
    for i in range(k, len(df_15m) - k):
        if all(highs[i] > highs[i - j] for j in range(1, k+1)) and all(highs[i] > highs[i + j] for j in range(1, k+1)):
            swing_highs.append(float(highs[i]))
        if all(lows[i] < lows[i - j] for j in range(1, k+1)) and all(lows[i] < lows[i + j] for j in range(1, k+1)):
            swing_lows.append(float(lows[i]))
            
    recent_swing_high = swing_highs[-1] if swing_highs else float(df_15m['High'].max())
    recent_swing_low  = swing_lows[-1] if swing_lows else float(df_15m['Low'].min())

    print("\n---------------- STEP 2: KEY LEVELS ----------------")
    print(f"📌 Key Liquidity High (Buy-side): {recent_swing_high:.2f}")
    print(f"📌 Key Liquidity Low  (Sell-side): {recent_swing_low:.2f}")

    # 5. Check if recent candles swept liquidity
    print("\n---------------- STEP 4: SWEEP STATUS --------------")
    swept_bullish = False
    swept_bearish = False
    sweep_low = 0.0
    sweep_high = 0.0
    sweep_time = ""
    
    for idx in range(-3, 0):
        candle = df_15m.iloc[idx]
        c_low = float(candle['Low'])
        c_high = float(candle['High'])
        c_close = float(candle['Close'])
        
        if recent_swing_low and c_low < recent_swing_low and c_close > recent_swing_low:
            swept_bullish = True
            sweep_low = c_low
            sweep_time = candle.name.strftime('%H:%M')
            print(f"🔥 BULLISH SWEEP at {sweep_time}! Low: {c_low:.2f}, Closed: {c_close:.2f}")
        if recent_swing_high and c_high > recent_swing_high and c_close < recent_swing_high:
            swept_bearish = True
            sweep_high = c_high
            sweep_time = candle.name.strftime('%H:%M')
            print(f"🔥 BEARISH SWEEP at {sweep_time}! High: {c_high:.2f}, Closed: {c_close:.2f}")

    if not swept_bullish and not swept_bearish:
        print("No sweep in recent candles. Waiting for setup.")

    # 6. Actionable Signal & Send Telegram
    print("\n================ ACTIONABLE SUMMARY ================")
    rr = 2.5
    if aligned_bullish and swept_bullish:
        entry = current_price
        sl = (sweep_low or (entry - 5.0)) - 1.0
        tp = entry + (entry - sl) * rr
        print(f"🚀 BUY SIGNAL READY!")
        print(f"   Entry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
        
        msg = (
            f"🚨 *NEW GOLD BUY (LONG) SIGNAL*\n\n"
            f"💰 *Entry Price:* {entry:.2f}\n"
            f"🛑 *Stop Loss:* {sl:.2f} (Protected sweep low)\n"
            f"🎯 *Take Profit:* {tp:.2f} (1:2.5 RR target)\n"
            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
            f"📌 *Setup:* 1H & 15M Bullish Aligned + Sweep at {sweep_time}"
        )
        send_telegram(msg)

    elif aligned_bearish and swept_bearish:
        entry = current_price
        sl = (sweep_high or (entry + 5.0)) + 1.0
        tp = entry - (sl - entry) * rr
        print(f"🔻 SELL SIGNAL READY!")
        print(f"   Entry: {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")

        msg = (
            f"🚨 *NEW GOLD SELL (SHORT) SIGNAL*\n\n"
            f"💰 *Entry Price:* {entry:.2f}\n"
            f"🛑 *Stop Loss:* {sl:.2f} (Protected sweep high)\n"
            f"🎯 *Take Profit:* {tp:.2f} (1:2.5 RR target)\n"
            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
            f"📌 *Setup:* 1H & 15M Bearish Aligned + Sweep at {sweep_time}"
        )
        send_telegram(msg)
    else:
        print("⏳ STATUS: WAITING FOR SETUP.")
        print("   -> Criteria not fully met yet.")
    print("====================================================\n")

if __name__ == '__main__':
    analyze_gold()
