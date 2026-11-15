import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

def analyze_gold():
    symbol = "GC=F" # Gold Futures (tracks XAU/USD closely)
    print(f"==================================================")
    print(f"📊 XAU/USD (Gold) Strategy Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"==================================================")
    
    # 1. Fetch 1-Hour data for macro trend
    print("Fetching 1-Hour data (Higher Timeframe)...")
    df_1h = yf.download(symbol, period="5d", interval="1h", progress=False)
    if df_1h.empty:
        print("Error: Could not retrieve 1H data.")
        return
    
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [col[0] for col in df_1h.columns]

    df_1h['EMA_20'] = df_1h['Close'].ewm(span=20, adjust=False).mean()
    df_1h['EMA_50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
    
    last_1h = df_1h.iloc[-1]
    prev_1h = df_1h.iloc[-2]
    
    htf_bullish = last_1h['Close'] > last_1h['EMA_20'] and last_1h['EMA_20'] >= last_1h['EMA_50']
    htf_bearish = last_1h['Close'] < last_1h['EMA_20'] and last_1h['EMA_20'] <= last_1h['EMA_50']
    htf_bias = "BULLISH 🟢" if htf_bullish else ("BEARISH 🔴" if htf_bearish else "NEUTRAL / CONSOLIDATION ⚪")
    
    print(f"1-Hour Trend Bias: {htf_bias} (Close: {last_1h['Close']:.2f})")
    
    # 2. Fetch 15-Minute data for execution & sweeps
    print("\nFetching 15-Minute data (Execution Timeframe)...")
    df_15m = yf.download(symbol, period="2d", interval="15m", progress=False)
    if df_15m.empty:
        print("Error: Could not retrieve 15M data.")
        return

    if isinstance(df_15m.columns, pd.MultiIndex):
        df_15m.columns = [col[0] for col in df_15m.columns]

    df_15m['EMA_20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
    df_15m['EMA_50'] = df_15m['Close'].ewm(span=50, adjust=False).mean()

    last_15m = df_15m.iloc[-1]
    
    ltf_bullish = last_15m['Close'] > last_15m['EMA_20'] and last_15m['EMA_20'] >= last_15m['EMA_50']
    ltf_bearish = last_15m['Close'] < last_15m['EMA_20'] and last_15m['EMA_20'] <= last_15m['EMA_50']
    ltf_bias = "BULLISH 🟢" if ltf_bullish else ("BEARISH 🔴" if ltf_bearish else "NEUTRAL / CONSOLIDATION ⚪")
    
    print(f"15-Minute Trend Bias: {ltf_bias} (Close: {last_15m['Close']:.2f})")
    
    # 3. Step 1 Alignment Check
    aligned_bullish = htf_bullish and ltf_bullish
    aligned_bearish = htf_bearish and ltf_bearish
    
    print("\n---------------- STEP 1: ALIGNMENT ----------------")
    if aligned_bullish:
        print("✅ ALIGNED: Both 1H and 15M are Bullish -> ONLY look for LONG setups.")
    elif aligned_bearish:
        print("✅ ALIGNED: Both 1H and 15M are Bearish -> ONLY look for SHORT setups.")
    else:
        print("⏳ MISALIGNED / CHOP: Higher timeframe and 15M are not in sync.")
        print("   Rule: Stay on the sidelines until both timeframes agree.")

    # 4. Swings and Liquidity Detection on 15M
    highs = df_15m['High'].values
    lows = df_15m['Low'].values
    closes = df_15m['Close'].values
    
    # Find recent swing highs and lows (pivot 5)
    swing_highs = []
    swing_lows = []
    k = 5
    for i in range(k, len(df_15m) - k):
        if all(highs[i] > highs[i - j] for j in range(1, k+1)) and all(highs[i] > highs[i + j] for j in range(1, k+1)):
            swing_highs.append((df_15m.index[i], highs[i]))
        if all(lows[i] < lows[i - j] for j in range(1, k+1)) and all(lows[i] < lows[i + j] for j in range(1, k+1)):
            swing_lows.append((df_15m.index[i], lows[i]))
            
    recent_swing_high = swing_highs[-1][1] if swing_highs else None
    recent_swing_low  = swing_lows[-1][1] if swing_lows else None

    print("\n---------------- STEP 2: KEY LEVELS ----------------")
    if recent_swing_high:
        print(f"📌 Key 15M Liquidity High (Resistance / Buy-side Liquidity): {recent_swing_high:.2f}")
    if recent_swing_low:
        print(f"📌 Key 15M Liquidity Low  (Support / Sell-side Liquidity)   : {recent_swing_low:.2f}")

    # 5. Check if recent candles swept liquidity
    print("\n---------------- STEP 4: SWEEP STATUS --------------")
    swept_bullish = False
    swept_bearish = False
    
    # check last 3 candles
    for idx in range(-3, 0):
        candle = df_15m.iloc[idx]
        if recent_swing_low and candle['Low'] < recent_swing_low and candle['Close'] > recent_swing_low:
            swept_bullish = True
            print(f"🔥 BULLISH LIQUIDITY SWEEP detected at {candle.name.strftime('%H:%M')}! Low reached {candle['Low']:.2f} and closed at {candle['Close']:.2f}")
        if recent_swing_high and candle['High'] > recent_swing_high and candle['Close'] < recent_swing_high:
            swept_bearish = True
            print(f"🔥 BEARISH LIQUIDITY SWEEP detected at {candle.name.strftime('%H:%M')}! High reached {candle['High']:.2f} and closed at {candle['Close']:.2f}")

    if not swept_bullish and not swept_bearish:
        print("No recent sweep in the last 3 candles. Waiting for liquidity to be grabbed.")

    # 6. Actionable Recommendation
    print("\n================ ACTIONABLE SUMMARY ================")
    if aligned_bullish and swept_bullish:
        entry = last_15m['Close']
        sl = (recent_swing_low or (entry - 5.0)) - 1.0
        tp = entry + (entry - sl) * 2.5
        print(f"🚀 BUY SIGNAL READY!")
        print(f"   Entry : {entry:.2f}")
        print(f"   SL    : {sl:.2f}")
        print(f"   TP    : {tp:.2f} (1:2.5 RR)")
    elif aligned_bearish and swept_bearish:
        entry = last_15m['Close']
        sl = (recent_swing_high or (entry + 5.0)) + 1.0
        tp = entry - (sl - entry) * 2.5
        print(f"🔻 SELL SIGNAL READY!")
        print(f"   Entry : {entry:.2f}")
        print(f"   SL    : {sl:.2f}")
        print(f"   TP    : {tp:.2f} (1:2.5 RR)")
    else:
        print("⏳ STATUS: WAITING FOR SETUP.")
        if not (aligned_bullish or aligned_bearish):
            print("   -> Reason: Timeframes are not aligned.")
        elif not (swept_bullish or swept_bearish):
            print("   -> Reason: Timeframes aligned, but no liquidity sweep at POI yet.")
    print("====================================================\n")

if __name__ == '__main__':
    analyze_gold()
