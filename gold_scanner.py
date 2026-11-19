import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf

# Karachi / Pakistan Standard Time (PKT = UTC+5)
PKT = timezone(timedelta(hours=5))

def get_karachi_time():
    """Returns the current datetime in Karachi / Pakistan Standard Time (PKT)."""
    return datetime.now(PKT)

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
            return True
        else:
            print(f"⚠️ Telegram Markdown send failed ({r.status_code}): {r.text}. Retrying with plain text...")
    except Exception as e:
        print(f"⚠️ Telegram request exception: {e}. Retrying with plain text...")

    # Try 2: Plain-text fallback
    try:
        clean_text = msg.replace("*", "").replace("_", "").replace("`", "")
        payload_plain = {"chat_id": recipient, "text": clean_text}
        r2 = requests.post(url, json=payload_plain, headers=headers, timeout=12)
        if r2.status_code == 200:
            print(f"✅ Telegram message delivered (plain text fallback) to chat {recipient}!")
            return True
        else:
            err_msg = f"❌ Telegram API returned Error {r2.status_code}: {r2.text}"
            print(err_msg)
            return False
    except Exception as e:
        print("❌ Telegram fallback request failed:", e)
        return False

def fetch_market_data():
    """Fetches 1H and 15M Gold market data and evaluates trend bias."""
    symbol = "GC=F"
    try:
        df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df_1h.empty:
            df_1h = yf.download("XAUUSD=X", period="5d", interval="1h", progress=False)
            if df_1h.empty:
                return None
        
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = [col[0] for col in df_1h.columns]

        df_1h['EMA_20'] = df_1h['Close'].ewm(span=20, adjust=False).mean()
        df_1h['EMA_50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
        last_1h = df_1h.iloc[-1]
        
        htf_bullish = bool(last_1h['Close'] > last_1h['EMA_20'] and last_1h['EMA_20'] >= last_1h['EMA_50'])
        htf_bearish = bool(last_1h['Close'] < last_1h['EMA_20'] and last_1h['EMA_20'] <= last_1h['EMA_50'])
        htf_bias = "BULLISH 🟢" if htf_bullish else ("BEARISH 🔴" if htf_bearish else "NEUTRAL / CHOP ⚪")

        df_15m = yf.download(symbol, period="5d", interval="15m", progress=False)
        if df_15m.empty:
            df_15m = yf.download("XAUUSD=X", period="5d", interval="15m", progress=False)
            if df_15m.empty:
                return None

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = [col[0] for col in df_15m.columns]

        df_15m['EMA_20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
        df_15m['EMA_50'] = df_15m['Close'].ewm(span=50, adjust=False).mean()

        last_15m = df_15m.iloc[-1]
        current_price = float(last_15m['Close'])

        ltf_bullish = bool(last_15m['Close'] > last_15m['EMA_20'] and last_15m['EMA_20'] >= last_15m['EMA_50'])
        ltf_bearish = bool(last_15m['Close'] < last_15m['EMA_20'] and last_15m['EMA_20'] <= last_15m['EMA_50'])
        ltf_bias = "BULLISH 🟢" if ltf_bullish else ("BEARISH 🔴" if ltf_bearish else "NEUTRAL / CHOP ⚪")

        aligned_bullish = htf_bullish and ltf_bullish
        aligned_bearish = htf_bearish and ltf_bearish

        if aligned_bullish:
            alignment_text = "ALIGNED BULLISH 🟢 (Looking for Buys only)"
        elif aligned_bearish:
            alignment_text = "ALIGNED BEARISH 🔴 (Looking for Sells only)"
        else:
            alignment_text = "MISALIGNED ⏳ (Waiting for 1H & 15M to agree)"

        # Swings and Liquidity
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

        # Check Sweeps (converted to Karachi PKT time)
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
            
            # Convert timestamp to Karachi PKT (UTC+5)
            c_time = candle.name
            if hasattr(c_time, "tzinfo") and c_time.tzinfo is not None:
                c_pkt = c_time.astimezone(PKT)
            else:
                c_pkt = c_time + pd.Timedelta(hours=5)
            fmt_time = c_pkt.strftime('%I:%M %p PKT')
            
            if recent_swing_low and c_low < recent_swing_low and c_close > recent_swing_low:
                swept_bullish = True
                sweep_low = c_low
                sweep_time = fmt_time
            if recent_swing_high and c_high > recent_swing_high and c_close < recent_swing_high:
                swept_bearish = True
                sweep_high = c_high
                sweep_time = fmt_time

        if aligned_bullish and swept_bullish:
            status_msg = "🔥 BUY SETUP CONFIRMED! Ready to enter."
        elif aligned_bearish and swept_bearish:
            status_msg = "🔥 SELL SETUP CONFIRMED! Ready to enter."
        elif aligned_bullish or aligned_bearish:
            status_msg = f"👀 WATCHING FOR SWEEP: Timeframes aligned, waiting for liquidity grab near ${recent_swing_low:.2f} / ${recent_swing_high:.2f}."
        else:
            status_msg = "⏳ WAITING FOR TREND ALIGNMENT: 1H and 15M pointing in different directions."

        return {
            "current_price": current_price,
            "htf_bias": htf_bias,
            "ltf_bias": ltf_bias,
            "alignment_text": alignment_text,
            "aligned_bullish": aligned_bullish,
            "aligned_bearish": aligned_bearish,
            "recent_swing_high": recent_swing_high,
            "recent_swing_low": recent_swing_low,
            "swept_bullish": swept_bullish,
            "swept_bearish": swept_bearish,
            "sweep_low": sweep_low,
            "sweep_high": sweep_high,
            "sweep_time": sweep_time,
            "status_msg": status_msg
        }
    except Exception as e:
        print("Error fetching market data:", e)
        return None

def check_user_messages_and_reply(mkt, last_offset=0):
    """Listens for user Telegram messages and replies immediately with live status in Karachi Time (PKT)!"""
    token, default_chat_id = get_telegram_creds()
    if not token or not mkt:
        return last_offset

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 3}
    if last_offset > 0:
        params["offset"] = last_offset

    try:
        r = requests.get(url, params=params, timeout=8)
        if r.status_code != 200:
            return last_offset

        data = r.json()
        results = data.get("result", [])
        if not results:
            return last_offset

        new_offset = last_offset
        for item in results:
            update_id = item.get("update_id", 0)
            if update_id >= new_offset:
                new_offset = update_id + 1

            msg_obj = item.get("message") or item.get("edited_message") or {}
            sender_id = msg_obj.get("chat", {}).get("id")
            text = msg_obj.get("text", "").strip()

            if sender_id and text:
                print(f"📩 Incoming command '{text}' from Telegram chat {sender_id}!")
                karachi_now = get_karachi_time().strftime('%Y-%m-%d %I:%M:%S %p')
                reply_msg = (
                    f"📊 *GOLD (XAU/USD) LIVE STATUS REPORT*\n"
                    f"⏰ *Time (Karachi):* {karachi_now} PKT\n\n"
                    f"💰 *Live Price:* ${mkt['current_price']:.2f}\n"
                    f"📈 *1-Hour Trend:* {mkt['htf_bias']}\n"
                    f"📉 *15-Min Trend:* {mkt['ltf_bias']}\n"
                    f"⚖️ *Alignment:* {mkt['alignment_text']}\n"
                    f"🔺 *Ceiling (High Liq):* ${mkt['recent_swing_high']:.2f}\n"
                    f"🔻 *Floor (Low Liq):* ${mkt['recent_swing_low']:.2f}\n\n"
                    f"📌 *Strategy Condition:* {mkt['status_msg']}\n\n"
                    f"🤖 *Bot Health:* 24/7 Cloud Listener is active. Send *update* anytime for live data!"
                )
                send_telegram(reply_msg, target_chat_id=sender_id)

        return new_offset
    except Exception as e:
        print("Telegram polling exception:", e)
        return last_offset

def send_daily_briefing(mkt):
    """Sends the daily market briefing in Karachi Time (PKT)."""
    today_str = get_karachi_time().strftime('%A, %b %d, %Y (%I:%M %p PKT)')
    msg = (
        f"🌅 *DAILY GOLD (XAU/USD) MARKET BRIEFING*\n"
        f"📅 *Date:* {today_str}\n\n"
        f"💰 *Current Price:* ${mkt['current_price']:.2f}\n"
        f"📈 *1-Hour Macro Trend:* {mkt['htf_bias']}\n"
        f"📉 *15-Minute Trend:* {mkt['ltf_bias']}\n"
        f"⚖️ *Alignment:* {mkt['alignment_text']}\n\n"
        f"🎯 *Key Levels for Today:*\n"
        f"🔺 *Major Resistance (Ceiling):* ${mkt['recent_swing_high']:.2f}\n"
        f"🔻 *Major Support (Floor):* ${mkt['recent_swing_low']:.2f}\n\n"
        f"📋 *Today's Strategy Plan:*\n"
        f"• Wait for 1H & 15M trend alignment before looking for trades.\n"
        f"• Watch for liquidity sweeps at key levels.\n"
        f"• Target quick 1:2.5 Risk-to-Reward on clean moves.\n\n"
        f"🤖 *Bot Status:* 24/7 Cloud scanner is active and watching. Send *update* anytime!"
    )
    return send_telegram(msg)

def run_continuous_scanner():
    """Runs a 14-minute continuous cloud scanning session."""
    token, chat_id = get_telegram_creds()
    masked_token = (token[:6] + "..." + token[-4:]) if len(token) > 10 else ("EMPTY" if not token else "INVALID")
    masked_chat = (chat_id[:3] + "..." + chat_id[-2:]) if len(chat_id) > 5 else (chat_id if chat_id else "EMPTY")

    karachi_start = get_karachi_time().strftime('%Y-%m-%d %I:%M:%S %p')

    print(f"==================================================")
    print(f"📊 Gold (XAU/USD) 24/7 Continuous Cloud Scanner Starting")
    print(f"Time: {karachi_start} PKT (Karachi Time)")
    print(f"Token Configured: {bool(token)} ({masked_token}) | Chat ID: {bool(chat_id)} ({masked_chat})")
    print(f"==================================================")

    # Initial Market Fetch
    mkt = fetch_market_data()
    if not mkt:
        print("Initial market data fetch failed. Retrying in 10s...")
        time.sleep(10)
        mkt = fetch_market_data()

    if not mkt:
        print("Market data unavailable currently.")
        log_step_summary("> ⚠️ Market data unavailable currently from data feed.")
        return

    log_step_summary(f"""### 🪙 Gold 24/7 Cloud Scanner Run Summary
- ⏰ **Scan Time (Karachi):** `{karachi_start} PKT`
- 🔑 **TELEGRAM_TOKEN Secret:** `{'Configured (' + masked_token + ')' if token else '❌ MISSING from Secrets'}`
- 💬 **TELEGRAM_CHAT_ID Secret:** `{'Configured (' + masked_chat + ')' if chat_id else '❌ MISSING from Secrets'}`
- 💰 **Current Gold Price:** `${mkt['current_price']:.2f}`
- ⚖️ **Alignment:** `{mkt['alignment_text']}`
- 📌 **Strategy Condition:** `{mkt['status_msg']}`
""")

    # 1. Check if Daily Cron or Test Run Trigger
    is_daily_cron = os.environ.get("IS_DAILY_CRON", "").lower() in ["true", "1", "yes"]
    is_test_run = os.environ.get("SEND_TEST", "").lower() in ["true", "1", "yes"]

    if is_daily_cron or is_test_run:
        print(f"Triggering briefing: is_daily_cron={is_daily_cron}, is_test_run={is_test_run}")
        briefing_delivered = send_daily_briefing(mkt)
        if is_test_run and not briefing_delivered:
            print("❌ Manual Test Dispatch failed to deliver Telegram message.")
            sys.exit(1)

    # 2. Continuous 14-Minute Active Listener & Scanner Loop
    TOTAL_LOOP_SECONDS = 840
    start_time = time.time()
    last_market_fetch_time = time.time()
    last_signal_sent = ""
    last_offset = 0

    print(f"🚀 Entering active live listener loop for {TOTAL_LOOP_SECONDS // 60} minutes...")
    print("Listening for Telegram commands (update, status, etc.) in real time!")

    while time.time() - start_time < TOTAL_LOOP_SECONDS:
        try:
            # A. Check and reply to user Telegram messages immediately!
            last_offset = check_user_messages_and_reply(mkt, last_offset=last_offset)

            # B. Periodic Market Data Refresh (every 60 seconds)
            now = time.time()
            if now - last_market_fetch_time >= 60:
                fresh_mkt = fetch_market_data()
                if fresh_mkt:
                    mkt = fresh_mkt
                    print(f"[{get_karachi_time().strftime('%I:%M:%S %p')} PKT] Price: ${mkt['current_price']:.2f} | {mkt['alignment_text']}")

                # C. Check Confirmed Trade Signals
                rr = 2.5
                if mkt['aligned_bullish'] and mkt['swept_bullish']:
                    signal_key = f"BUY_{mkt['sweep_time']}"
                    if signal_key != last_signal_sent:
                        entry = mkt['current_price']
                        sl = (mkt['sweep_low'] or (entry - 5.0)) - 1.0
                        tp = entry + (entry - sl) * rr
                        msg = (
                            f"🚀 *CONFIRMED GOLD BUY (LONG) SIGNAL*\n\n"
                            f"💰 *Entry Price:* ${entry:.2f}\n"
                            f"🛑 *Stop Loss:* ${sl:.2f} (Protected sweep low)\n"
                            f"🎯 *Take Profit:* ${tp:.2f} (1:2.5 RR target)\n"
                            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
                            f"📌 *Setup:* 1H & 15M Bullish Aligned + Sweep at {mkt['sweep_time']}"
                        )
                        send_telegram(msg)
                        last_signal_sent = signal_key

                elif mkt['aligned_bearish'] and mkt['swept_bearish']:
                    signal_key = f"SELL_{mkt['sweep_time']}"
                    if signal_key != last_signal_sent:
                        entry = mkt['current_price']
                        sl = (mkt['sweep_high'] or (entry + 5.0)) + 1.0
                        tp = entry - (sl - entry) * rr
                        msg = (
                            f"🔻 *CONFIRMED GOLD SELL (SHORT) SIGNAL*\n\n"
                            f"💰 *Entry Price:* ${entry:.2f}\n"
                            f"🛑 *Stop Loss:* ${sl:.2f} (Protected sweep high)\n"
                            f"🎯 *Take Profit:* ${tp:.2f} (1:2.5 RR target)\n"
                            f"⚖️ *Risk/Reward:* 1 : 2.5\n"
                            f"📌 *Setup:* 1H & 15M Bearish Aligned + Sweep at {mkt['sweep_time']}"
                        )
                        send_telegram(msg)
                        last_signal_sent = signal_key

                last_market_fetch_time = now

            # Sleep briefly to avoid CPU spike
            time.sleep(2)

        except Exception as loop_err:
            print("Scanner loop exception:", loop_err)
            time.sleep(4)

    print(f"\n✅ 14-Minute scanning cycle completed successfully. Handing over to next scheduled run.")

if __name__ == '__main__':
    run_continuous_scanner()
