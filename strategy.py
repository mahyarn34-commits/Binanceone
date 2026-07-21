"""
موتور استراتژی:
مرحله ۱) طبقه‌بندی روند در 1H و 4H با EMA9/21 + RSI14 + MACD
مرحله ۲) اگه روند 1H و 4H هم‌جهت بودن (نماد "همسو")، وارد مرحله ۳ می‌شه
مرحله ۳) روی M15 با EMA9/21 + RSI14 + MACD + Bollinger + VWAP + SuperTrend
         سیگنال دقیق BUY/SELL/WAIT به همراه Entry/SL/TP تولید می‌کنه
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from indicators import ema, rsi, macd, bollinger_bands, atr, supertrend, session_vwap


@dataclass
class TrendResult:
    trend: str          # BULLISH / BEARISH / NEUTRAL
    score: int           # از -4 تا +4
    rsi: float
    macd_hist: float
    close: float


@dataclass
class EntrySignal:
    signal: str          # BUY / SELL / WAIT
    reason: str
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rr: Optional[float] = None


def classify_trend(df: pd.DataFrame) -> TrendResult:
    close = df["close"]
    ema9 = ema(close, 9)
    ema21 = ema(close, 21)
    rsi14 = rsi(close, 14)
    _, _, hist = macd(close)

    last_close = close.iloc[-1]
    score = 0
    score += 1 if ema9.iloc[-1] > ema21.iloc[-1] else -1
    score += 1 if last_close > ema21.iloc[-1] else -1
    score += 1 if rsi14.iloc[-1] > 50 else -1
    score += 1 if hist.iloc[-1] > 0 else -1

    if score >= 2:
        trend = "BULLISH"
    elif score <= -2:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    return TrendResult(
        trend=trend,
        score=score,
        rsi=round(float(rsi14.iloc[-1]), 1),
        macd_hist=round(float(hist.iloc[-1]), 6),
        close=float(last_close),
    )


def m15_entry_signal(df: pd.DataFrame, higher_tf_bias: str) -> EntrySignal:
    """
    higher_tf_bias: 'BULLISH' یا 'BEARISH' یا 'NEUTRAL' — نتیجه‌ی هم‌جهتی 1H/4H
    فقط در جهت هم‌سو با تایم بالاتر سیگنال صادر می‌شه (فیلتر HTF).
    """
    close = df["close"]
    ema9 = ema(close, 9)
    ema21 = ema(close, 21)
    rsi14 = rsi(close, 14)
    _, _, hist = macd(close)
    upper_bb, mid_bb, lower_bb = bollinger_bands(close, 20, 2.0)
    vwap = session_vwap(df)
    st_dir, st_line = supertrend(df, period=10, multiplier=3.0)
    atr14 = atr(df, 14)

    last = -1
    price = float(close.iloc[last])
    e9 = float(ema9.iloc[last])
    e21 = float(ema21.iloc[last])
    r = float(rsi14.iloc[last])
    h = float(hist.iloc[last])
    v = float(vwap.iloc[last]) if not pd.isna(vwap.iloc[last]) else price
    st = int(st_dir.iloc[last])
    a = float(atr14.iloc[last]) if not pd.isna(atr14.iloc[last]) else (price * 0.005)

    if higher_tf_bias == "BULLISH" and st == 1:
        conditions = {
            "قیمت بالای VWAP": price > v,
            "EMA9 بالای EMA21": e9 > e21,
            "RSI در بازه سالم (40-65)": 40 <= r <= 65,
            "MACD هیستوگرام مثبت": h > 0,
            "SuperTrend صعودی": st == 1,
        }
        if all(conditions.values()):
            entry = price
            stop_loss = min(e21, entry) - 0.5 * a
            take_profit = entry + 2 * (entry - stop_loss)
            rr = (take_profit - entry) / (entry - stop_loss) if entry != stop_loss else None
            return EntrySignal("BUY", "همه شرایط BUY هم‌جهت با روند بالاتر برقراره", entry, round(stop_loss, 6), round(take_profit, 6), rr)
        missing = [k for k, ok in conditions.items() if not ok]
        return EntrySignal("WAIT", "منتظر تکمیل شرایط BUY — نقص: " + "، ".join(missing))

    if higher_tf_bias == "BEARISH" and st == -1:
        conditions = {
            "قیمت زیر VWAP": price < v,
            "EMA9 زیر EMA21": e9 < e21,
            "RSI در بازه سالم (35-60)": 35 <= r <= 60,
            "MACD هیستوگرام منفی": h < 0,
            "SuperTrend نزولی": st == -1,
        }
        if all(conditions.values()):
            entry = price
            stop_loss = max(e21, entry) + 0.5 * a
            take_profit = entry - 2 * (stop_loss - entry)
            rr = (entry - take_profit) / (stop_loss - entry) if entry != stop_loss else None
            return EntrySignal("SELL", "همه شرایط SELL هم‌جهت با روند بالاتر برقراره", entry, round(stop_loss, 6), round(take_profit, 6), rr)
        missing = [k for k, ok in conditions.items() if not ok]
        return EntrySignal("WAIT", "منتظر تکمیل شرایط SELL — نقص: " + "، ".join(missing))

    return EntrySignal("WAIT", "روند 1H/4H هم‌جهت با SuperTrend M15 نیست یا خنثی است")


def analyze_symbol(symbol: str, df_4h: pd.DataFrame, df_1h: pd.DataFrame, df_15m: pd.DataFrame) -> dict:
    trend_4h = classify_trend(df_4h)
    trend_1h = classify_trend(df_1h)

    if trend_4h.trend == trend_1h.trend and trend_4h.trend in ("BULLISH", "BEARISH"):
        aligned = True
        bias = trend_4h.trend
    else:
        aligned = False
        bias = "NEUTRAL"

    m15 = m15_entry_signal(df_15m, bias) if aligned else EntrySignal("WAIT", "روند 1H و 4H هم‌جهت نیست")

    return {
        "symbol": symbol,
        "trend_4h": trend_4h,
        "trend_1h": trend_1h,
        "aligned": aligned,
        "bias": bias,
        "m15": m15,
    }
