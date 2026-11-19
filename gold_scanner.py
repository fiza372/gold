import os
import sys
import time
import requests
from datetime import datetime
import pandas as pd
import yfinance as yf

def log_step_summary(content):
    """Writes status reports to GitHub Actions Step Summary for instant visibility."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(content + "\n\n")
        except Exception as e:
            print("Failed to write to GITHUB_STEP_SUMMARY:", e)

def get_telegram_creds():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip().strip('"').strip("'")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")
    return token, chat_id

def send_telegram(msg, target_chat_id=None):
    token, default_chat_id = get_telegram_creds()
    recipient = str(target_chat_id or default_chat_id).strip()
    
    if not token:
        err = "❌ Error: TELEGRAM_TOKEN secret is missing or empty in GitHub Settings!"
        print(err)
        log_step_summary("> ❌ **Telegram Error**: `TELEGRAM_TOKEN` secret is NOT set or empty in GitHub Secrets.")
        return False
    if not recipient:
        err = "❌ Error: TELEGRAM_CHAT_ID secret is missing or empty in GitHub Settings!"
        print(err)
        log_step_summary("> ❌ **Telegram Error**: `TELEGRAM_CHAT_ID` secret is NOT set or empty in GitHub Secrets.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Try 1: Send with Markdown
    try:
        payload = {"chat_id": recipient, "text": msg, "parse_mode": "Markdown"}
        r = requests.post(url, json=payload, headers=headers, timeout=12)
        if r.status_code == 200:
            print(f"✅ Telegram message delivered successfully to chat {recipient}!")
            log_step_summary(f"> ✅ **Telegram Delivery**: Delivered successfully to chat `{recipient}` (200 OK)!")
            return True
        else:
            print(f"⚠️ Telegram Markdown send failed ({r.status_code}): {r.text}. Retrying with plain text...")
    except Exception as e:
        print(f"⚠️ Telegram request exception: {e}. Retrying with plain text...")

    # Try 2: Robust plain-text fallback (immune to Markdown formatting errors)
    try:
        clean_text = msg.replace("*", "").replace("_", "").replace("`", "")
        payload_plain = {"chat_id": recipient, "text": clean_text}
        r2 = requests.post(url, json=payload_plain, headers=headers, timeout=12)
        if r2.status_code == 200:
            print(f"✅ Telegram message delivered (plain text fallback) to chat {recipient}!")
            log_step_summary(f"> ✅ **Telegram Delivery**: Delivered (plain text fallback) to chat `{recipient}` (200 OK)!")
            return True
        else:
            err_msg = f"❌ Telegram API returned Error {r2.status_code}: {r2.text}"
            print(err_msg)
            
            hint = ""
            if r2.status_code == 401:
                hint = "**Cause:** Bot token is INVALID or REVOKED! Go to Telegram `@BotFather` to generate a new token, then update `TELEGRAM_TOKEN` in GitHub Secrets."
            elif r2.status_code == 400 and "chat not found" in r2.text.lower():
                hint = f"**Cause:** Chat ID `{recipient}` not found. Ensure you are using your NUMERIC ID from `@userinfobot`, not your @username."
            elif r2.status_code == 403:
                hint = "**Cause:** Bot was never started or is blocked! You MUST search your bot on Telegram and press the **'Start'** button."
            
            log_step_summary(f"> ❌ **Telegram Send Failed**: `{r2.status_code} {r2.text}`\n>\n> 💡 {hint}")
            return False
    except Exception as e:
        print("❌ Telegram fallback request failed:", e)
        log_step_summary(f"> ❌ **Telegram Connection Failed**: `{e}`")
        return False

def check_user_messages_and_reply(current_price, htf_bias, ltf_bias, alignment_text, high_liq, low_liq, status_msg):
    """Checks if the user sent any message/update to the bot and replies directly!"""
    token, default_chat_id = get_telegram_creds()
    if not token:
        print("Skipping Telegram message check: No token provided.")
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        r = requests.get(url, timeout=10)
        if r.status_code == 401:
            print("❌ getUpdates returned 401 Unauthorized: Bot token is invalid or revoked!")
            log_step_summary("> ⚠️ **Bot Token Invalid (401)**: The bot token provided is rejected by Telegram. Please update it with a new one from `@BotFather`.")
            return
        if r.status_code != 200:
            print(f"⚠️ getUpdates returned status {r.status_code}: {r.text}")
            return
        
        data = r.json()
        results = data.get("result", [])
        if not results:
            print("No pending messages in Telegram bot inbox.")
            return
        
        print(f"Found {len(results)} updates in Telegram inbox.")
        last_update_id = results[-1].get("update_id", 0)
        
        # Collect distinct chats that sent messages
        chats_to_reply = set()
        
        for item in results:
            msg_obj = item.get("message") or item.get("edited_message") or {}
            text = msg_obj.get("text", "").strip()
            sender_id = msg_obj.get("chat", {}).get("id")
            if sender_id:
                chats_to_reply.add(str(sender_id))
                print(f"📩 Recognized message '{text}' from chat {sender_id}!")

        # Reply directly with live status
        if chats_to_reply:
            reply_msg = (
                f"📊 *GOLD (XAU/USD) LIVE STATUS REPORT*\n"
                f"⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                f"💰 *Live Price:* ${current_price:.2f}\n"
                f"📈 *1-Hour Trend:* {htf_bias}\n"
                f"📉 *15-Min Trend:* {ltf_bias}\n"
                f"⚖️ *Alignment:* {alignment_text}\n"
                f"🔺 *Ceiling (Buy-side High):* ${high_liq:.2f}\n"
                f"🔻 *Floor (Sell-side Low):* ${low_liq:.2f}\n\n"
                f"📌 *Strategy Status:* {status_msg}\n\n"
                f"🤖 *Bot Health:* Running 24/7 in cloud. Send any text anytime for live data!"
            )
            for chat in chats_to_reply:
                send_telegram(reply_msg, target_chat_id=chat)
                
            # Clear read messages offset
            requests.get(f"{url}?offset={last_update_id + 1}", timeout=5)
    except Exception as e:
        print("Note on Telegram check exception:", e)

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
    print("Sending Daily Market Briefing to Telegram...")
    return send_telegram(msg)

def analyze_gold():
    symbol = "GC=F" # Gold Futures (tracks spot Gold XAU/USD)
    
    token, chat_id = get_telegram_creds()
    masked_token = (token[:6] + "..." + token[-4:]) if len(token) > 10 else ("EMPTY" if not token else "INVALID")
    masked_chat = (chat_id[:3] + "..." + chat_id[-2:]) if len(chat_id) > 5 else (chat_id if chat_id else "EMPTY")

    print(f"==================================================")
    print(f"📊 Gold (XAU/USD) Smart Cloud Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Token Configured: {bool(token)} ({masked_token}) | Chat ID: {bool(chat_id)} ({masked_chat})")
    print(f"==================================================")
    
    log_step_summary(f"""### 🪙 Gold 24/7 Cloud Scanner Run Summary
- ⏰ **Scan Time (UTC):** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`
- 🔑 **TELEGRAM_TOKEN Secret:** `{'Configured (' + masked_token + ')' if token else '❌ MISSING from Secrets'}`
- 💬 **TELEGRAM_CHAT_ID Secret:** `{'Configured (' + masked_chat + ')' if chat_id else '❌ MISSING from Secrets'}`
""")

    # 1. Fetch 1-Hour data for macro trend
    print("Fetching 1-Hour data...")
    df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
    if df_1h.empty:
        df_1h = yf.download("XAUUSD=X", period="5d", interval="1h", progress=False)
        if df_1h.empty:
            print("Market data unavailable currently.")
            log_step_summary("> ⚠️ Market data unavailable currently from data feed.")
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

    log_step_summary(f"""### 📊 Market Status
- **Current Price:** `${current_price:.2f}`
- **1-Hour Trend:** `{htf_bias}`
- **15-Min Trend:** `{ltf_bias}`
- **Alignment:** `{alignment_text}`
- **Strategy Condition:** `{status_msg}`
""")

    # A. AUTOMATIC DAILY BRIEFING OR TEST RUN TRIGGER
    is_daily_cron = os.environ.get("IS_DAILY_CRON", "").lower() in ["true", "1", "yes"]
    is_test_run = os.environ.get("SEND_TEST", "").lower() in ["true", "1", "yes"]
    
    if is_daily_cron or is_test_run:
        print(f"Triggering briefing: is_daily_cron={is_daily_cron}, is_test_run={is_test_run}")
        briefing_delivered = send_daily_briefing(current_price, htf_bias, ltf_bias, alignment_text, recent_swing_high, recent_swing_low)
        if is_test_run and not briefing_delivered:
            print("❌ Manual Test Dispatch failed to deliver Telegram message. Exiting with error so GitHub shows the failure!")
            sys.exit(1)

    # B. Check and reply directly to user commands (/update, /daily, /status, or any message)
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
