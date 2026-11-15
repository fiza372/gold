import os
import json
import threading
import time
import requests
from datetime import datetime
import pandas as pd
import yfinance as yf
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# State storage
LATEST_ANALYSIS = {}
CONFIG = {
    "entry_mode": "Conservative (MSS Confirmation)",
    "risk_reward": 2.5,
    "telegram_token": os.environ.get("TELEGRAM_TOKEN", "").strip(),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
    "auto_scan": True,
    "scan_interval": 30 # seconds
}

def send_telegram_alert(message):
    token = CONFIG.get("telegram_token", "").strip()
    chat_id = CONFIG.get("telegram_chat_id", "").strip()
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=5)
            print("Telegram alert sent successfully!")
        except Exception as e:
            print("Failed to send Telegram alert:", e)

def analyze_strategy():
    global LATEST_ANALYSIS
    symbol = "GC=F" # Gold Futures (tracks spot Gold XAU/USD closely)
    
    try:
        # 1. Higher Timeframe (1H)
        df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
        if df_1h.empty:
            return LATEST_ANALYSIS

        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = [col[0] for col in df_1h.columns]

        df_1h['EMA_20'] = df_1h['Close'].ewm(span=20, adjust=False).mean()
        df_1h['EMA_50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()

        last_1h = df_1h.iloc[-1]
        htf_bullish = bool(last_1h['Close'] > last_1h['EMA_20'] and last_1h['EMA_20'] >= last_1h['EMA_50'])
        htf_bearish = bool(last_1h['Close'] < last_1h['EMA_20'] and last_1h['EMA_20'] <= last_1h['EMA_50'])
        
        if htf_bullish:
            htf_bias = "BULLISH"
        elif htf_bearish:
            htf_bias = "BEARISH"
        else:
            htf_bias = "NEUTRAL"

        # 2. Execution Timeframe (15M)
        df_15m = yf.download(symbol, period="2d", interval="15m", progress=False)
        if df_15m.empty:
            return LATEST_ANALYSIS

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = [col[0] for col in df_15m.columns]

        df_15m['EMA_20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
        df_15m['EMA_50'] = df_15m['Close'].ewm(span=50, adjust=False).mean()

        last_15m = df_15m.iloc[-1]
        current_price = float(last_15m['Close'])

        ltf_bullish = bool(last_15m['Close'] > last_15m['EMA_20'] and last_15m['EMA_20'] >= last_15m['EMA_50'])
        ltf_bearish = bool(last_15m['Close'] < last_15m['EMA_20'] and last_15m['EMA_20'] <= last_15m['EMA_50'])

        if ltf_bullish:
            ltf_bias = "BULLISH"
        elif ltf_bearish:
            ltf_bias = "BEARISH"
        else:
            ltf_bias = "NEUTRAL"

        # 3. Alignment
        alignment_bullish = htf_bullish and ltf_bullish
        alignment_bearish = htf_bearish and ltf_bearish
        
        if alignment_bullish:
            alignment_status = "ALIGNED_BULLISH"
        elif alignment_bearish:
            alignment_status = "ALIGNED_BEARISH"
        else:
            alignment_status = "MISALIGNED"

        # 4. Swings and Liquidity Levels on 15M
        highs = df_15m['High'].values
        lows = df_15m['Low'].values
        k = 4
        swing_highs = []
        swing_lows = []
        for i in range(k, len(df_15m) - k):
            if all(highs[i] > highs[i - j] for j in range(1, k+1)) and all(highs[i] > highs[i + j] for j in range(1, k+1)):
                swing_highs.append(float(highs[i]))
            if all(lows[i] < lows[i - j] for j in range(1, k+1)) and all(lows[i] < lows[i + j] for j in range(1, k+1)):
                swing_lows.append(float(lows[i]))

        recent_swing_high = float(swing_highs[-1]) if swing_highs else float(df_15m['High'].max())
        recent_swing_low  = float(swing_lows[-1]) if swing_lows else float(df_15m['Low'].min())

        # 5. Check for Liquidity Sweeps
        swept_bullish = False
        swept_bearish = False
        sweep_candle_time = ""
        sweep_low = 0.0
        sweep_high = 0.0

        for idx in range(-4, 0):
            c = df_15m.iloc[idx]
            c_low = float(c['Low'])
            c_high = float(c['High'])
            c_close = float(c['Close'])
            
            if recent_swing_low and c_low < recent_swing_low and c_close > recent_swing_low:
                swept_bullish = True
                sweep_low = c_low
                sweep_candle_time = c.name.strftime('%H:%M')
            if recent_swing_high and c_high > recent_swing_high and c_close < recent_swing_high:
                swept_bearish = True
                sweep_high = c_high
                sweep_candle_time = c.name.strftime('%H:%M')

        # 6. Signal Determination
        signal = None
        rr = CONFIG.get("risk_reward", 2.5)
        
        if alignment_bullish and swept_bullish:
            entry = current_price
            sl = sweep_low - 0.8
            tp = round(entry + (entry - sl) * rr, 2)
            signal = {
                "type": "BUY",
                "entry": round(entry, 2),
                "sl": round(sl, 2),
                "tp": tp,
                "rr": f"1:{rr}",
                "reason": f"1H & 15M Bullish Aligned + Liquidity swept at {sweep_candle_time}"
            }
        elif alignment_bearish and swept_bearish:
            entry = current_price
            sl = sweep_high + 0.8
            tp = round(entry - (sl - entry) * rr, 2)
            signal = {
                "type": "SELL",
                "entry": round(entry, 2),
                "sl": round(sl, 2),
                "tp": tp,
                "rr": f"1:{rr}",
                "reason": f"1H & 15M Bearish Aligned + Liquidity swept at {sweep_candle_time}"
            }

        # 7. Format Candlesticks for Lightweight Charts
        chart_data = []
        for idx_time, row in df_15m.iterrows():
            chart_data.append({
                "time": int(idx_time.timestamp()),
                "open": round(float(row['Open']), 2),
                "high": round(float(row['High']), 2),
                "low": round(float(row['Low']), 2),
                "close": round(float(row['Close']), 2)
            })

        LATEST_ANALYSIS = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "current_price": round(current_price, 2),
            "htf_bias": htf_bias,
            "ltf_bias": ltf_bias,
            "alignment_status": alignment_status,
            "recent_swing_high": round(recent_swing_high, 2),
            "recent_swing_low": round(recent_swing_low, 2),
            "swept_bullish": swept_bullish,
            "swept_bearish": swept_bearish,
            "sweep_time": sweep_candle_time,
            "signal": signal,
            "chart_data": chart_data
        }

        # Trigger Telegram alert if new signal
        if signal:
            msg = (
                f"🚨 *NEW GOLD ({signal['type']}) SIGNAL*\n"
                f"💰 *Entry:* {signal['entry']}\n"
                f"🛑 *Stop Loss:* {signal['sl']}\n"
                f"🎯 *Take Profit:* {signal['tp']}\n"
                f"⚖️ *Risk/Reward:* {signal['rr']}\n"
                f"📌 *Setup:* {signal['reason']}"
            )
            send_telegram_alert(msg)

        return LATEST_ANALYSIS

    except Exception as e:
        print("Analysis error:", e)
        return LATEST_ANALYSIS

# Background scanner thread
def background_scanner():
    while True:
        try:
            if CONFIG.get("auto_scan", True):
                analyze_strategy()
        except Exception as e:
            print("Background loop error:", e)
        time.sleep(CONFIG.get("scan_interval", 30))

threading.Thread(target=background_scanner, daemon=True).start()

# Web routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    if not LATEST_ANALYSIS:
        analyze_strategy()
    return jsonify({
        "status": "success",
        "data": LATEST_ANALYSIS,
        "config": CONFIG
    })

@app.route('/api/scan_now', methods=['POST'])
def scan_now():
    res = analyze_strategy()
    return jsonify({"status": "success", "data": res})

@app.route('/api/save_config', methods=['POST'])
def save_config():
    data = request.json or {}
    for k in ["entry_mode", "risk_reward", "telegram_token", "telegram_chat_id", "auto_scan", "scan_interval"]:
        if k in data:
            CONFIG[k] = data[k]
    return jsonify({"status": "success", "config": CONFIG})

@app.route('/api/test_telegram', methods=['POST'])
def test_telegram():
    data = request.json or {}
    token = data.get("token") or CONFIG.get("telegram_token")
    chat_id = data.get("chat_id") or CONFIG.get("telegram_chat_id")
    if not token or not chat_id:
        return jsonify({"status": "error", "message": "Token or Chat ID missing"}), 400
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": "✅ *Gold Scalping Strategy Bot is connected!* You will receive real-time Gold trade alerts here.",
            "parse_mode": "Markdown"
        }, timeout=5)
        if resp.status_code == 200:
            return jsonify({"status": "success", "message": "Test alert sent to Telegram successfully!"})
        else:
            return jsonify({"status": "error", "message": resp.text}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Initial scan
    analyze_strategy()
    port = int(os.environ.get("PORT", 5000))
    print(f"Gold Strategy UI Server running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
