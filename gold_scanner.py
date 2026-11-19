import os
import sys
import time
import requests
from datetime import datetime
import pandas as pd
import yfinance as yf

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
    """Checks if the user sent 'update', 'status', 'daily', or any command on Telegram and replies back!"""
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
        user_asked = False
        
        for item in results:
            msg_obj = item.get("message", {})
            text = msg_obj.get("text", "").lower().strip()
            if any(cmd in text for cmd in ["update", "status", "daily", "check", "gold", "price", "/start"]):
                user_asked = True

        if user_asked:
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
                f"🤖 *Bot Health:* Running 24/7 in the cloud. You can send *update* or *daily* anytime!"
            )
            send_telegram(reply)
            requests.get(f"{url}?offset={last_update_id + 1}", timeout=5)
            
    except Exception as e:
        print("Note on Telegram check:", e)

def send_daily_briefing(current_price, htf_bias, ltf_bias, alignment_text, high_liq, low_liq):
    """Sends the formatted daily morning market update."""
    today_str = datetime.now().strftime('%A, %b %d, %Y')
    msg = (
        f"🌅 *DAILY GOLD (XAU/USD) MARKET BRIEFING*\n"
        f"📅 *Date:* {today_str}\n\n"
        f"💰 *Current Price:* ${current_price:.2f}\n"
        f"📈 *1-Hour Macro Trend:* {htf_bias}\n"
        f"📉 *15-Minute Trend:* {ltf_bias}\n"
        f"⚖️ *Alignment:* {alignment_text}\n\n"
        f"🎯 *Key Levels for Today:*\n"
        f"🔺 *Major Resistance (Ceiling):* ${high_liq:.2f}\n"
        f"🔻 *Major Support (Floor):* ${low_liq:.2f}\n\n"
        f"📋 *Today's Strategy Plan:*\n"
        f"• Wait for 1H & 15M trend alignment before looking for trades.\n"
        f"• Watch for liquidity sweeps at key levels.\n"
        f"• Target quick 1:2.5 Risk-to-Reward on clean moves.\n\n"
        f"🤖 *Bot Status:* 24/7 Cloud scanner is active and watching. Have a profitable trading day!"
    )
    print("Sending automatic Daily Market Briefing to Telegram...")
    send_telegram(msg)

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
        status_msg = f"👀 WATCHING FOR SWEEP: Timeframes aligned, waiting for liquidity grab near ${recent_swing_low:.2f} / ${recent_swing_high:.2f}."
    else:
        status_msg = "⏳ WAITING FOR TREND ALIGNMENT: 1H and 15M pointing in different directions."

    # A. AUTOMATIC DAILY BRIEFING (Triggered daily at 04:00 UTC / 9:00 AM local or via DAILY_UPDATE=true)
    is_daily_cron = os.environ.get("IS_DAILY_CRON", "").lower() in ["true", "1", "yes"]
    is_test_run = os.environ.get("SEND_TEST", "").lower() in ["true", "1", "yes"]
    
    if is_daily_cron or is_test_run:
        send_daily_briefing(current_price, htf_bias, ltf_bias, alignment_text, recent_swing_high, recent_swing_low)

    # B. Check and reply to user commands (/update, /daily, /status)
    check_user_messages_and_reply(current_price, htf_bias, ltf_bias, alignment_text, recent_swing_high, recent_swing_low, status_msg)

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

    print(f"\nScan complete. Status: {status_msg}")

if __name__ == '__main__':
    analyze_gold()
