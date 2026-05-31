import os, time, requests
import pandas as pd
import ta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
TWELVEDATA_KEY  = os.getenv("TWELVEDATA_KEY",  "YOUR_TWELVEDATA_KEY")
BASE_URL = "https://api.twelvedata.com"

ASSETS = {
    "BTC/USD": "₿ BTC/USD (24/7)",
    "ETH/USD": "⟠ ETH/USD (24/7)",
    "GBP/JPY": "🇬🇧 GBP/JPY",
    "XAU/USD": "🥇 Gold",
    "GBP/USD": "🇬🇧 GBP/USD",
    "EUR/USD": "🇪🇺 EUR/USD",
    "USD/JPY": "🇯🇵 USD/JPY",
    "USD/CHF": "🇨🇭 USD/CHF",
    "AUD/USD": "🇦🇺 AUD/USD",
    "USD/CAD": "🇨🇦 USD/CAD",
    "NZD/USD": "🇳🇿 NZD/USD",
    "EUR/JPY": "🇯🇵 EUR/JPY",
    "EUR/GBP": "🇪🇺 EUR/GBP",
}

def fetch_candles(symbol, interval="5min", outputsize=100, retries=3):
    params = {"symbol": symbol, "interval": interval,
              "outputsize": outputsize, "apikey": TWELVEDATA_KEY}
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(f"{BASE_URL}/time_series", params=params, timeout=10)
            data = r.json()
            if data.get("status") == "error":
                return None
            values = data.get("values", [])
            if not values:
                return None
            df = pd.DataFrame(values)
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
            return df.iloc[::-1].reset_index(drop=True)
        except requests.exceptions.Timeout:
            time.sleep(5)
        except Exception:
            time.sleep(3)
    return None

def calculate_indicators(df):
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    open_ = df["open"]

    rsi_s    = ta.momentum.RSIIndicator(close, window=14).rsi()
    rsi      = rsi_s.iloc[-1]
    rsi_prev = rsi_s.iloc[-2]

    macd_obj  = ta.trend.MACD(close)
    macd_line = macd_obj.macd().iloc[-1]
    macd_sig  = macd_obj.macd_signal().iloc[-1]
    macd_hist = macd_obj.macd_diff().iloc[-1]
    prev_hist = macd_obj.macd_diff().iloc[-2]

    bb        = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper  = bb.bollinger_hband().iloc[-1]
    bb_lower  = bb.bollinger_lband().iloc[-1]
    bb_mid    = bb.bollinger_mavg().iloc[-1]
    bb_pct    = bb.bollinger_pband().iloc[-1]
    bb_width  = (bb_upper - bb_lower) / bb_mid * 100

    ema9      = ta.trend.EMAIndicator(close, window=9).ema_indicator()
    ema20     = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50     = ta.trend.EMAIndicator(close, window=50).ema_indicator()

    adx_obj   = ta.trend.ADXIndicator(high, low, close, window=14)
    adx       = adx_obj.adx().iloc[-1]
    adx_pos   = adx_obj.adx_pos().iloc[-1]
    adx_neg   = adx_obj.adx_neg().iloc[-1]

    stoch     = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
    stoch_k   = stoch.stoch().iloc[-1]
    stoch_d   = stoch.stoch_signal().iloc[-1]
    stoch_kp  = stoch.stoch().iloc[-2]

    cci       = ta.trend.CCIIndicator(high, low, close, window=20).cci().iloc[-1]
    wr        = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r().iloc[-1]
    atr       = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
    atr_pct   = atr / close.iloc[-1] * 100

    c0_o, c0_c = open_.iloc[-1], close.iloc[-1]
    c1_o, c1_c = open_.iloc[-2], close.iloc[-2]
    c2_o, c2_c = open_.iloc[-3], close.iloc[-3]
    c0_h, c0_l = high.iloc[-1], low.iloc[-1]
    c0_body    = abs(c0_c - c0_o)
    c0_range   = max(c0_h - c0_l, 0.00001)
    c0_bull    = c0_c > c0_o
    c1_bull    = c1_c > c1_o
    c2_bull    = c2_c > c2_o

    return {
        "price":       close.iloc[-1],
        "rsi":         rsi,        "rsi_prev":  rsi_prev,
        "macd":        macd_line,  "sig":       macd_sig,
        "hist":        macd_hist,  "prev_hist": prev_hist,
        "bb_upper":    bb_upper,   "bb_lower":  bb_lower,
        "bb_mid":      bb_mid,     "bb_pct":    bb_pct,
        "bb_width":    bb_width,
        "ema9":        ema9.iloc[-1],  "ema9p":   ema9.iloc[-2],
        "ema20":       ema20.iloc[-1], "ema20p":  ema20.iloc[-2],
        "ema50":       ema50.iloc[-1],
        "adx":         adx, "adx_pos": adx_pos, "adx_neg": adx_neg,
        "stoch_k":     stoch_k, "stoch_d": stoch_d, "stoch_kp": stoch_kp,
        "cci":         cci, "wr": wr, "atr_pct": atr_pct,
        "three_bull":  c0_bull  and c1_bull  and c2_bull,
        "three_bear":  not c0_bull and not c1_bull and not c2_bull,
        "strong_bull": c0_bull  and c0_body > c0_range * 0.6,
        "strong_bear": not c0_bull and c0_body > c0_range * 0.6,
        "hammer":      not c0_bull and (c0_l < c0_o - c0_range * 0.45),
        "shooting":    c0_bull  and (c0_h > c0_c + c0_range * 0.45),
    }

def get_signal(ind):
    rsi     = ind["rsi"]
    stoch_k = ind["stoch_k"]
    wr      = ind["wr"]
    cci     = ind["cci"]

    # ══ REVERSAL DETECTION — KEY FIX ══════════════════════
    # Jab price top pe ho aur girne wali ho — CALL block
    overbought_count = 0
    if rsi > 70:       overbought_count += 1
    if stoch_k > 80:   overbought_count += 1
    if wr > -20:       overbought_count += 1
    if cci > 150:      overbought_count += 1

    # Jab price bottom pe ho aur uthne wali ho — PUT block
    oversold_count = 0
    if rsi < 30:       oversold_count += 1
    if stoch_k < 20:   oversold_count += 1
    if wr < -80:       oversold_count += 1
    if cci < -150:     oversold_count += 1

    # Reversal warning flags
    reversal_down = overbought_count >= 3  # 3+ indicators say overbought
    reversal_up   = oversold_count >= 3    # 3+ indicators say oversold

    votes = []

    # 1. EMA trend
    e9, e20, e50 = ind["ema9"], ind["ema20"], ind["ema50"]
    if e9 > e20 > e50:   votes += [1, 1, 1]
    elif e9 < e20 < e50: votes += [-1, -1, -1]
    elif e20 > e50:      votes += [1]
    else:                votes += [-1]

    if ind["ema9"] > ind["ema20"] and ind["ema9p"] <= ind["ema20p"]:
        votes += [1, 1]
    elif ind["ema9"] < ind["ema20"] and ind["ema9p"] >= ind["ema20p"]:
        votes += [-1, -1]

    # 2. ADX — weighted
    adx = ind["adx"]
    adx_bull = ind["adx_pos"] > ind["adx_neg"]
    if adx > 40:
        votes += [1, 1, 1] if adx_bull else [-1, -1, -1]
    elif adx > 25:
        votes += [1, 1] if adx_bull else [-1, -1]
    else:
        votes += [1] if adx_bull else [-1]

    # 3. RSI — with reversal awareness
    if rsi < 30:         votes += [1, 1]
    elif rsi > 70:
        # Overbought — but only add bear vote, not bull
        votes += [-1]
    elif rsi < 50:       votes += [1]
    else:                votes += [-1]

    if ind["rsi"] > ind["rsi_prev"]: votes += [1]
    else:                            votes += [-1]

    # 4. MACD
    if ind["macd"] > ind["sig"]:
        votes += [1]
        if ind["hist"] > ind["prev_hist"]: votes += [1]
    else:
        votes += [-1]
        if ind["hist"] < ind["prev_hist"]: votes += [-1]

    # 5. Stochastic — reversal aware
    if stoch_k < 20:
        votes += [1, 1]
    elif stoch_k > 80:
        votes += [-1]  # overbought = only 1 bear vote
        if stoch_k < ind["stoch_kp"]:
            votes += [-1]  # turning down = extra bear
    elif stoch_k < 50:  votes += [1]
    else:               votes += [-1]

    # 6. CCI
    if cci < -100:   votes += [1, 1]
    elif cci > 100:  votes += [-1]
    elif cci < 0:    votes += [1]
    else:            votes += [-1]

    # 7. Williams %R
    if wr < -80:    votes += [1, 1]
    elif wr > -20:  votes += [-1]
    elif wr < -50:  votes += [1]
    else:           votes += [-1]

    # 8. Bollinger Bands
    price = ind["price"]
    if price <= ind["bb_lower"]:   votes += [1, 1]
    elif price >= ind["bb_upper"]: votes += [-1, -1]
    elif ind["bb_pct"] < 0.5:     votes += [1]
    else:                          votes += [-1]

    # 9. Candles
    if ind["three_bull"]:    votes += [1, 1]
    elif ind["three_bear"]:  votes += [-1, -1]
    if ind["strong_bull"]:   votes += [1]
    elif ind["strong_bear"]: votes += [-1]
    if ind["hammer"]:        votes += [1]
    if ind["shooting"]:      votes += [-1]

    # ══ REVERSAL OVERRIDE ═════════════════════════════════
    # Agar 3+ indicators say reversal — force correct direction
    if reversal_down:
        votes += [-1, -1, -1]  # push toward PUT
    if reversal_up:
        votes += [1, 1, 1]     # push toward CALL

    total   = len(votes)
    bull_v  = votes.count(1)
    bear_v  = votes.count(-1)
    direction = "CALL" if bull_v >= bear_v else "PUT"
    winner_v  = max(bull_v, bear_v)

    raw_agreement = winner_v / total
    confidence = round(min(45 + (raw_agreement - 0.5) * 333, 95), 1)

    # ADX boost
    if adx > 40:   confidence = min(confidence + 8, 95)
    elif adx > 25: confidence = min(confidence + 4, 95)

    # Reversal penalty — agar direction mismatch with reversal
    if reversal_down and direction == "CALL":
        confidence = max(confidence - 20, 35)
    if reversal_up and direction == "PUT":
        confidence = max(confidence - 20, 35)

    if confidence >= 72:
        grade = "A"; win_pct = 65; loss_pct = 35
    elif confidence >= 60:
        grade = "B"; win_pct = 59; loss_pct = 41
    elif confidence >= 52:
        grade = "C"; win_pct = 53; loss_pct = 47
    else:
        grade = "D"; win_pct = 48; loss_pct = 52

    # Build reasons
    reasons = []
    if e9 > e20 > e50:   reasons.append("EMA 9>20>50 — Strong uptrend")
    elif e9 < e20 < e50: reasons.append("EMA 9<20<50 — Strong downtrend")
    elif e20 > e50:      reasons.append("EMA 20>50 — Uptrend")
    else:                reasons.append("EMA 20<50 — Downtrend")

    reasons.append(f"ADX {adx:.0f} {'🔥Strong' if adx>40 else '💪Medium' if adx>25 else '😴Weak'} — {'Bullish' if adx_bull else 'Bearish'}")
    reasons.append(f"RSI {rsi:.1f} — {'🔴 Overbought — reversal risk!' if rsi>70 else '🟢 Oversold' if rsi<30 else 'Below 50' if rsi<50 else 'Above 50'}")
    reasons.append(f"MACD {'▲ Bullish' if ind['macd']>ind['sig'] else '▼ Bearish'}")
    reasons.append(f"Stoch {stoch_k:.0f} — {'🔴 Overbought' if stoch_k>80 else '🟢 Oversold' if stoch_k<20 else 'Below 50' if stoch_k<50 else 'Above 50'}")
    reasons.append(f"CCI {cci:.0f} — {'🔴 Overbought' if cci>100 else '🟢 Oversold' if cci<-100 else 'Neg' if cci<0 else 'Pos'}")
    reasons.append(f"W%R {wr:.0f} — {'🔴 Overbought' if wr>-20 else '🟢 Oversold' if wr<-80 else 'Low zone' if wr<-50 else 'High zone'}")

    if reversal_down:
        reasons.append("⚠️ REVERSAL DOWN — 3+ indicators overbought!")
    if reversal_up:
        reasons.append("⚠️ REVERSAL UP — 3+ indicators oversold!")

    if ind["three_bull"]:    reasons.append("3 green candles 📈")
    elif ind["three_bear"]:  reasons.append("3 red candles 📉")
    if ind["strong_bull"]:   reasons.append("Strong bull candle")
    elif ind["strong_bear"]: reasons.append("Strong bear candle")

    return direction, confidence, grade, win_pct, loss_pct, "\n".join(reasons), bull_v, bear_v, adx, reversal_down, reversal_up

def build_msg(symbol, interval, ind, direction, confidence, grade, win_pct, loss_pct, reasons, bull_v, bear_v, adx, rev_down, rev_up):
    dir_emoji   = "🟢" if direction == "CALL" else "🔴"
    grade_emoji = {"A": "🏆", "B": "✅", "C": "⚡", "D": "⚠️"}[grade]
    filled = int(confidence // 10)
    bar    = "█" * filled + "░" * (10 - filled)

    e9, e20, e50 = ind["ema9"], ind["ema20"], ind["ema50"]
    if e9 > e20 > e50:   trend = "📈 Strong UP"
    elif e9 < e20 < e50: trend = "📉 Strong DOWN"
    elif e20 > e50:      trend = "📈 Mild UP"
    else:                trend = "📉 Mild DOWN"

    adx_icon = "🔥" if adx > 40 else ("💪" if adx > 25 else "😴")

    adx_msg = ""
    if adx < 20:
        adx_msg = "\n⚠️ *Market flat — BTC/USD ya GBP/JPY try karo*"

    reversal_msg = ""
    if rev_down:
        reversal_msg = "\n🚨 *REVERSAL WARNING — Price girne wali hai!*"
    elif rev_up:
        reversal_msg = "\n🚨 *REVERSAL WARNING — Price uthne wali hai!*"

    advice = {
        "A": "✅ Strong signal — trade karo",
        "B": "✅ Good signal — trade kar sakte ho",
        "C": "⚡ Moderate — chhoti amount lagao",
        "D": "⚠️ Weak — better asset try karo",
    }[grade]

    if rev_down and direction == "CALL":
        advice = "🚨 CALL mat lo — reversal down risk!"
    elif rev_up and direction == "PUT":
        advice = "🚨 PUT mat lo — reversal up risk!"

    lines = [
        f"📊 *{symbol}* — {interval}",
        "━━━━━━━━━━━━━━━━━━",
        f"{trend}  {adx_icon} ADX: `{adx:.0f}`",
        adx_msg,
        reversal_msg,
        "",
        f"{dir_emoji} *Signal: {direction}*   {grade_emoji} *Grade: {grade}*",
        f"Confidence: `{confidence}%`",
        f"`{bar}`",
        "",
        f"🎯 *Win: {win_pct}%*  ❌ *Loss: {loss_pct}%*",
        f"🗳️ Bull: `{bull_v}`  Bear: `{bear_v}`",
        "",
        "🔍 *Analysis:*",
    ]
    for r in reasons.split("\n"):
        if r: lines.append(f"• {r}")

    lines += ["", f"💡 {advice}",
              "", "📌 _Educational only. Apni risk par trade karein._"]
    return "\n".join(lines)

async def scan_best(query, ctx):
    await query.edit_message_text("🔍 Scanning all assets for best ADX...", parse_mode="Markdown")
    results = []
    for symbol in ASSETS:
        df = fetch_candles(symbol, "5min", outputsize=60)
        if df is None or len(df) < 30:
            continue
        try:
            adx_obj = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
            adx_val = adx_obj.adx().iloc[-1]
            results.append((symbol, adx_val))
        except Exception:
            continue

    if not results:
        await query.edit_message_text("❌ Scan fail hua.", parse_mode="Markdown")
        return

    results.sort(key=lambda x: x[1], reverse=True)
    top3 = results[:3]
    lines = ["🏆 *Best Assets Right Now:*", ""]
    for i, (sym, adx_v) in enumerate(top3):
        icon = "🥇" if i == 0 else ("🥈" if i == 1 else "🥉")
        bar_len = min(int(adx_v / 10), 10)
        lines.append(f"{icon} *{sym}* — ADX: `{adx_v:.0f}` `{'█'*bar_len}`")
    lines += ["", "👆 Inhe analyze karo — best signals milenge!"]

    kb = [[InlineKeyboardButton(f"🔄 {top3[i][0]}", callback_data=f"analyze|{top3[i][0]}|5min")]
          for i in range(len(top3))]
    kb.append([InlineKeyboardButton("📋 All Assets", callback_data="asset_menu")])
    await query.edit_message_text("\n".join(lines), parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(kb))

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🔍 Best Asset Scan", callback_data="scan_best")],
        [InlineKeyboardButton("🔄 EUR/USD (5m)",    callback_data="analyze|EUR/USD|5min")],
        [InlineKeyboardButton("📋 All Assets",       callback_data="asset_menu")],
    ]
    await update.message.reply_text(
        "👋 *MyPocketBot V9*\n"
        "━━━━━━━━━━━━━━━━\n"
        "🆕 *Reversal Detection* — overbought/oversold block\n"
        "🆕 *Jab RSI 70+ aur Stoch 80+* — CALL automatically weaken\n"
        "✅ Best Asset Scanner\n"
        "✅ ADX warning system\n"
        "✅ 13 assets 24/7\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 Pehle *Best Asset Scan* karo!",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def cb_scan_best(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await scan_best(query, ctx)

async def cb_asset_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    items = list(ASSETS.items())
    kb = []
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][1], callback_data=f"analyze|{items[i][0]}|5min")]
        if i+1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][1], callback_data=f"analyze|{items[i+1][0]}|5min"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔍 Best Asset Scan", callback_data="scan_best")])
    await query.edit_message_text("🌍 *Asset chunein:*",
                                   reply_markup=InlineKeyboardMarkup(kb),
                                   parse_mode="Markdown")

async def cb_analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, symbol, interval = query.data.split("|")
    await query.edit_message_text(f"⏳ *{symbol}* {interval} analyzing...", parse_mode="Markdown")
    df = fetch_candles(symbol, interval, outputsize=100)
    if df is None or len(df) < 55:
        await query.edit_message_text("❌ Data fetch nahi hua. Baad mein try karein.", parse_mode="Markdown")
        return
    ind = calculate_indicators(df)
    direction, confidence, grade, win_pct, loss_pct, reasons, bull_v, bear_v, adx, rev_down, rev_up = get_signal(ind)
    msg = build_msg(symbol, interval, ind, direction, confidence, grade, win_pct, loss_pct,
                    reasons, bull_v, bear_v, adx, rev_down, rev_up)
    kb = [
        [InlineKeyboardButton("🔄 Refresh",        callback_data=f"analyze|{symbol}|{interval}"),
         InlineKeyboardButton("📋 Assets",          callback_data="asset_menu")],
        [InlineKeyboardButton("1m",  callback_data=f"analyze|{symbol}|1min"),
         InlineKeyboardButton("5m",  callback_data=f"analyze|{symbol}|5min"),
         InlineKeyboardButton("15m", callback_data=f"analyze|{symbol}|15min"),
         InlineKeyboardButton("1h",  callback_data=f"analyze|{symbol}|1h")],
        [InlineKeyboardButton("🔍 Best Asset Scan", callback_data="scan_best")],
    ]
    await query.edit_message_text(msg, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(kb))

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_scan_best,  pattern="^scan_best$"))
    app.add_handler(CallbackQueryHandler(cb_asset_menu, pattern="^asset_menu$"))
    app.add_handler(CallbackQueryHandler(cb_analyze,    pattern="^analyze\\|"))
    print("MyPocketBot V9 chal raha hai...")
    app.run_polling()

if __name__ == "__main__":
    main()
