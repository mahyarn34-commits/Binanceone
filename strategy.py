"""
موتور استراتژی (Price-Action / Smart-Money-Concepts محور)

معماری سه‌تایم‌فریمی:
- 4H = فیلتر روند اصلی (EMA50/200 + Market Structure) — فقط تشخیص جهت، بدون سیگنال
- 1H = تأیید روند (EMA20/50 + Structure + Volume) — فقط تأیید، بدون سیگنال
- M15 = تنها تایم‌فریمی که وارد معامله می‌شه

ورود فقط وقتی صادر می‌شه که 4H و 1H هم‌جهت باشن و امتیاز M15 (از سیستم
امتیازدهی زیر) از آستانه‌ی config.SIGNAL_SCORE_THRESHOLD بیشتر باشه.

سیستم امتیازدهی (جمعاً از ۱۰۰):
    4H Trend              +20
    1H Trend              +15
    BOS (M15)             +15
    Liquidity Sweep       +20
    Supply/Demand Zone    +10
    VWAP                  +5
    Volume                +5
    Confirmation Candle   +10
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

import config
from indicators import ema, atr, session_vwap
import market_structure as ms
import liquidity as liq
import supply_demand as sd
import candles


SCORE_WEIGHTS = {
    "4h_trend": 20,
    "1h_trend": 15,
    "bos": 15,
    "liquidity_sweep": 20,
    "supply_demand": 10,
    "vwap": 5,
    "volume": 5,
    "confirmation_candle": 10,
}


@dataclass
class EntrySignal:
    signal: str  # BUY / SELL / WAIT
    reason: str
    score: int = 0
    max_score: int = 100
    breakdown: Dict[str, bool] = field(default_factory=dict)
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rr: Optional[float] = None


def _m15_score(df: pd.DataFrame, direction: str) -> "tuple[int, Dict[str, bool], dict]":
    """امتیازدهی M15 برای یک جهت مشخص (BULLISH/BEARISH). خروجی: (امتیاز، breakdown، اطلاعات کمکی)"""
    close = df["close"]
    price = float(close.iloc[-1])

    bos = ms.has_bos_in_direction(df, direction)

    sweep = liq.detect_liquidity_sweep(df, direction)

    zones = sd.find_zones(df)
    zone = sd.price_in_zone(price, zones, direction)

    vwap_series = session_vwap(df)
    vwap_val = float(vwap_series.iloc[-1]) if not pd.isna(vwap_series.iloc[-1]) else price
    vwap_ok = price > vwap_val if direction == "BULLISH" else price < vwap_val

    vol_ma = df["volume"].rolling(20).mean()
    volume_ok = bool(df["volume"].iloc[-1] > vol_ma.iloc[-1]) if not pd.isna(vol_ma.iloc[-1]) else False

    confirm_candle = candles.has_confirmation_candle(df, direction)

    breakdown = {
        "bos": bos,
        "liquidity_sweep": sweep.swept,
        "supply_demand": zone is not None,
        "vwap": vwap_ok,
        "volume": volume_ok,
        "confirmation_candle": confirm_candle,
    }

    # 4h_trend و 1h_trend قبلاً به‌عنوان شرط ورود به این تابع (aligned) چک شدن،
    # پس امتیازشون همیشه به‌صورت کامل به مجموع اضافه می‌شه — در غیر این صورت
    # حداکثر امتیاز قابل‌دستیابی ۶۵ می‌موند و هیچ‌وقت به آستانه‌ی ۷۰ نمی‌رسید.
    score = SCORE_WEIGHTS["4h_trend"] + SCORE_WEIGHTS["1h_trend"]
    score += sum(SCORE_WEIGHTS[k] for k, ok in breakdown.items() if ok)

    breakdown = {"4h_trend": True, "1h_trend": True, **breakdown}

    extra = {"zone": zone, "sweep": sweep, "vwap": vwap_val}
    return score, breakdown, extra


def _build_signal(df: pd.DataFrame, direction: str, score: int, breakdown: Dict[str, bool], extra: dict) -> EntrySignal:
    close = df["close"]
    price = float(close.iloc[-1])
    a = atr(df, 14)
    atr_val = float(a.iloc[-1]) if not pd.isna(a.iloc[-1]) else price * 0.005

    zone = extra["zone"]

    if direction == "BULLISH":
        base_sl = zone.price_low if zone else price - atr_val
        stop_loss = min(base_sl, price) - 0.25 * atr_val
        take_profit = price + config.MIN_RISK_REWARD * (price - stop_loss)
        rr = (take_profit - price) / (price - stop_loss) if price != stop_loss else None
        signal = "BUY"
    else:
        base_sl = zone.price_high if zone else price + atr_val
        stop_loss = max(base_sl, price) + 0.25 * atr_val
        take_profit = price - config.MIN_RISK_REWARD * (stop_loss - price)
        rr = (price - take_profit) / (stop_loss - price) if price != stop_loss else None
        signal = "SELL"

    return EntrySignal(
        signal=signal,
        reason=f"امتیاز {score}/100 از آستانه‌ی {config.SIGNAL_SCORE_THRESHOLD} عبور کرد",
        score=score,
        breakdown=breakdown,
        entry=round(price, 6),
        stop_loss=round(stop_loss, 6),
        take_profit=round(take_profit, 6),
        rr=rr,
    )


def m15_entry_signal(df: pd.DataFrame, higher_tf_bias: str) -> EntrySignal:
    if higher_tf_bias not in ("BULLISH", "BEARISH"):
        return EntrySignal("WAIT", "روند 1H/4H هم‌جهت یا قطعی نیست")

    score, breakdown, extra = _m15_score(df, higher_tf_bias)

    if score >= config.SIGNAL_SCORE_THRESHOLD:
        return _build_signal(df, higher_tf_bias, score, breakdown, extra)

    missing = [k for k, ok in breakdown.items() if not ok]
    return EntrySignal(
        "WAIT",
        f"امتیاز {score}/100 (آستانه {config.SIGNAL_SCORE_THRESHOLD}) — نقص در: " + "، ".join(missing),
        score=score,
        breakdown=breakdown,
    )


def analyze_symbol(symbol: str, df_4h: pd.DataFrame, df_1h: pd.DataFrame, df_15m: pd.DataFrame) -> dict:
    trend_4h = ms.classify_major_trend(df_4h)
    trend_1h_confirm = ms.confirm_trend_1h(df_1h, trend_4h.trend)

    aligned = trend_4h.trend in ("BULLISH", "BEARISH") and trend_1h_confirm.trend == trend_4h.trend
    bias = trend_4h.trend if aligned else "NEUTRAL"

    m15 = m15_entry_signal(df_15m, bias) if aligned else EntrySignal("WAIT", "روند 1H با 4H هم‌جهت نیست")

    return {
        "symbol": symbol,
        "trend_4h": trend_4h,
        "trend_1h": trend_1h_confirm,
        "aligned": aligned,
        "bias": bias,
        "m15": m15,
    }
