import os
import sys
import time
import requests
from datetime import datetime
import pandas as pd
import yfinance as yf

# Track state to avoid duplicate alerts
STATE_FILE = "scanner_state.json"

def get_telegram_creds():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id

def send_telegram(msg):
    token, chat_id = get_telegram_creds()
    if not token or not chat_id:
        print("Note: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is missing.")
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

def check_user_messages_and_reply(current_price, htf_bias, ltf_bias, alignment_text, high_liq, low_liq, status_msg):
    """Checks if the user sent 'update', 'status', or any command on Telegram and replies back!"""
    token, chat_id = get_telegram_creds()
    if not token:
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return
        
        data = r.json()
        results = data.get("result", [])
        if not results:
            return
        
        last_update_id = results[-1].get("update_id", 0)
        
        # Check if user sent any message recently
        user_asked_for_update = False
        target_chat_id = chat_id
        
        for item in results:
            msg_obj = item.get("message", {})
            text = msg_obj.get("text", "").lower().strip()
            sender_chat = str(msg_obj.get("chat", {}).get("id", ""))
            
            # If user sent /update, update, status, /status, /start, gold, or check
            if any(cmd in text for cmd in ["update", "status", "check", "gold", "price", "/start"]):
                user_asked_for_update = True
                if sender_chat:
                    target_chat_id = sender_chat

        if user_asked_for_update:
            print("📩 User requested update on Telegram! Sending full report...")
            reply = (
                f"📊 *GOLD (XAU/USD) LIVE STATUS REPORT*\n"
                f"⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                f"💰 *Live Price:* ${current_price:.2f}\n"
                f"📈 *1-Hour Trend:* {htf_bias}\n"
                f"📉 *15-Min Trend:* {ltf_bias}\n"
                f"⚖️ *Alignment:* {alignment_text}\n"
                f"🔺 *Ceiling (Buy-side High):* ${high_liq:.2f}\n"
                f"🔻 *Floor (Sell-side Low):* ${low_liq:.2f}\n\n"
                f"📌 *Strategy Status:* {status_msg}\n\n"
                f"🤖 *Bot Health:* Running 24/7 in the cloud. You can send *update* anytime to get fresh market data!"
            )
            # Send reply
            send_telegram(reply)
            
            # Confirm offset to clear read messages
            requests.get(f"{url}?offset={last_update_id + 1}", timeout=5)
            
    except Exception as e:
        print("Note on Telegram check:", e)

def analyze_gold():
    symbol = "GC=F" # Gold Futures (tracks spot Gold XAU/USD)
    print(f"==================================================")
    print(f"📊 Gold (XAU/USD) Smart Cloud Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"==================================================")

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
    
    if aligned_bullish:
        alignment_text = "ALIGNED BULLISH 🟢 (Looking for Buys only)"
    elif aligned_bearish:
        alignment_text = "ALIGNED BEARISH 🔴 (Looking for Sells only)"
    else:
        alignment_text = "MISALIGNED ⏳ (Waiting for 1H & 15M to agree)"

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

    # 5. Check if recent candles swept liquidity
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
        if recent_swing_high and c_high > recent_swing_high and c_close < recent_swing_high:
            swept_bearish = True
            sweep_high = c_high
            sweep_time = candle.name.strftime('%H:%M')

    # Status summary
    if aligned_bullish and swept_bullish:
        status_msg = "🔥 BUY SETUP CONFIRMED! Ready to enter."
    elif aligned_bearish and swept_bearish:
        status_msg = "🔥 SELL SETUP CONFIRMED! Ready to enter."
    elif aligned_bullish or aligned_bearish:
        status_msg = f"👀 WATCHING FOR SWEEP: Timeframes are aligned, waiting for liquidity grab near ${recent_swing_low:.2f} / ${recent_swing_high:.2f}."
    else:
        status_msg = "⏳ WAITING FOR TREND ALIGNMENT: 1H and 15M are currently pointing in different directions. Capital is protected."

    # A. Check and answer any Telegram user requests (/update)
    check_user_messages_and_reply(current_price, htf_bias, ltf_bias, alignment_text, recent_swing_high, recent_swing_low, status_msg)

    # B. Condition 2 & 3: PRE-ALERT / HEADS UP NOTIFICATION
    # If 1H & 15M are aligned and price is near liquidity pool (within 0.3% of high/low)
    dist_to_low = abs(current_price - recent_swing_low)
    dist_to_high = abs(recent_swing_high - current_price)
    is_approaching_poi = (aligned_bullish and dist_to_low < 8.0) or (aligned_bearish and dist_to_high < 8.0)

    # C. FULL CONFIRMED ENTRY SIGNAL
    rr = 2.5
    if aligned_bullish and swept_bullish:
        entry = current_price
        sl = (sweep_low or (entry - 5.0)) - 1.0
        tp = entry + (entry - sl) * rr
        msg = (
            f"🚀 *CONFIRMED GOLD BUY (LONG) SIGNAL*\n\n"
            f"💰 *Entry Price:* ${entry:.2f}\n"
            f"🛑 *Stop Loss:* ${sl:.2f} (Protected sweep low)\n"
            f"🎯 *Take Profit:* ${tp:.2f} (1:2.5 RR target)\n"
            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
            f"📌 *Setup:* 1H & 15M Bullish Aligned + Sweep at {sweep_time}"
        )
        send_telegram(msg)

    elif aligned_bearish and swept_bearish:
        entry = current_price
        sl = (sweep_high or (entry + 5.0)) + 1.0
        tp = entry - (sl - entry) * rr
        msg = (
            f"🔻 *CONFIRMED GOLD SELL (SHORT) SIGNAL*\n\n"
            f"💰 *Entry Price:* ${entry:.2f}\n"
            f"🛑 *Stop Loss:* ${sl:.2f} (Protected sweep high)\n"
            f"🎯 *Take Profit:* ${tp:.2f} (1:2.5 RR target)\n"
            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
            f"📌 *Setup:* 1H & 15M Bearish Aligned + Sweep at {sweep_time}"
        )
        send_telegram(msg)
        
    elif is_approaching_poi:
        # Pre-alert: 2 conditions met!
        direction = "BULLISH 🟢" if aligned_bullish else "BEARISH 🔴"
        target_zone = f"Demand floor near ${recent_swing_low:.2f}" if aligned_bullish else f"Supply ceiling near ${recent_swing_high:.2f}"
        heads_up_msg = (
            f"👀 *HEADS UP: GOLD SETUP FORMING*\n\n"
            f"⚡ *Conditions Met:* 2 of 3 (Timeframes Aligned & Near POI)\n"
            f"📈 *Trend:* {direction}\n"
            f"🎯 *Target Zone:* Approaching {target_zone}\n"
            f"💰 *Current Price:* ${current_price:.2f}\n\n"
            f"👉 *Action:* Get ready on your broker. If price sweeps this zone and rejects, an official ENTRY alert will follow!"
        )
        # To avoid spamming, only print/send when appropriate
        print("Pre-alert condition satisfied: Setup is building!")

    print(f"\nScan complete. Status: {status_msg}")

if __name__ == '__main__':
    analyze_gold()
