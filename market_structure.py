"""
ماژول مستقل: تشخیص Market Structure

خروجی این ماژول صرفاً «اطلاعات» است (طبق قانون پروژه) — تصمیم‌گیری نهایی
در strategy.py انجام می‌شه.

مفاهیم پیاده‌سازی‌شده:
- Swing High / Swing Low (به روش Fractal با K کندل سمت چپ و راست)
- HH / HL / LH / LL بر مبنای مقایسه‌ی هر Swing با Swing هم‌نوع قبلی
- BOS (Break Of Structure): شکست یک Swing در جهت روند جاری (ادامه‌دهنده)
- CHoCH (Change Of Character): شکست یک Swing در خلاف جهت روند جاری (هشدار برگشت)
- روند اصلی با EMA50/EMA200 + آخرین رویداد ساختاری تعیین می‌شه
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional

import pandas as pd

from indicators import ema

SwingLabel = Literal["HH", "HL", "LH", "LL"]


@dataclass
class Swing:
    index: int
    price: float
    kind: str  # "high" یا "low"
    label: Optional[SwingLabel] = None


@dataclass
class StructureEvent:
    type: Literal["BOS", "CHoCH", "NONE"]
    direction: Literal["BULLISH", "BEARISH", "NONE"]
    broken_level: Optional[float] = None
    index: Optional[int] = None


@dataclass
class TrendResult:
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    ema_fast: float
    ema_slow: float
    last_event: StructureEvent
    swings: List[Swing] = field(default_factory=list)


def find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> List[Swing]:
    """Swing High/Low به روش Fractal ساده"""
    highs = df["high"].values
    lows = df["low"].values
    swings: List[Swing] = []

    for i in range(left, len(df) - right):
        window_high = highs[i - left : i + right + 1]
        if highs[i] == window_high.max() and (window_high == highs[i]).sum() == 1:
            swings.append(Swing(index=i, price=float(highs[i]), kind="high"))

        window_low = lows[i - left : i + right + 1]
        if lows[i] == window_low.min() and (window_low == lows[i]).sum() == 1:
            swings.append(Swing(index=i, price=float(lows[i]), kind="low"))

    swings.sort(key=lambda s: s.index)
    return swings


def label_swings(swings: List[Swing]) -> List[Swing]:
    """به هر Swing برچسب HH/HL/LH/LL نسبت به آخرین Swing هم‌نوع قبلی می‌ده"""
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None

    for s in swings:
        if s.kind == "high":
            if last_high is not None:
                s.label = "HH" if s.price > last_high.price else "LH"
            last_high = s
        else:
            if last_low is not None:
                s.label = "HL" if s.price > last_low.price else "LL"
            last_low = s
    return swings


def detect_last_structure_event(df: pd.DataFrame, swings: List[Swing], prior_trend: str) -> StructureEvent:
    """
    آخرین رویداد BOS/CHoCH رو با مقایسه‌ی close قیمت بعد از هر Swing با
    سطح همون Swing تشخیص می‌ده.

    prior_trend: روند قبل از این رویداد ("BULLISH"/"BEARISH"/"NEUTRAL") —
    برای تشخیص اینکه شکست هم‌جهت (BOS) بوده یا خلاف‌جهت (CHoCH).
    """
    close = df["close"]
    labeled = [s for s in swings if s.label]
    if not labeled:
        return StructureEvent(type="NONE", direction="NONE")

    last_swing_high = next((s for s in reversed(labeled) if s.kind == "high"), None)
    last_swing_low = next((s for s in reversed(labeled) if s.kind == "low"), None)

    best_event: Optional[StructureEvent] = None

    if last_swing_high is not None:
        broke_above = close.iloc[last_swing_high.index + 1 :] > last_swing_high.price
        if broke_above.any():
            break_idx = broke_above.idxmax()
            direction = "BULLISH"
            ev_type = "BOS" if prior_trend == "BULLISH" else "CHoCH"
            best_event = StructureEvent(ev_type, direction, last_swing_high.price, int(break_idx))

    if last_swing_low is not None:
        broke_below = close.iloc[last_swing_low.index + 1 :] < last_swing_low.price
        if broke_below.any():
            break_idx = broke_below.idxmax()
            direction = "BEARISH"
            ev_type = "BOS" if prior_trend == "BEARISH" else "CHoCH"
            candidate = StructureEvent(ev_type, direction, last_swing_low.price, int(break_idx))
            if best_event is None or candidate.index > best_event.index:
                best_event = candidate

    return best_event or StructureEvent(type="NONE", direction="NONE")


def classify_major_trend(df: pd.DataFrame, fast: int = 50, slow: int = 200) -> TrendResult:
    """
    روند اصلی (برای تایم‌فریم 4H): جهت پایه از EMA50 vs EMA200،
    و ساختار (Swing/BOS/CHoCH) به‌عنوان تأییدیه‌ی اضافه.
    """
    ema_fast = ema(df["close"], fast)
    ema_slow = ema(df["close"], slow)

    ef = float(ema_fast.iloc[-1])
    es = float(ema_slow.iloc[-1])

    base_trend = "BULLISH" if ef > es else "BEARISH" if ef < es else "NEUTRAL"

    swings = label_swings(find_swings(df))
    event = detect_last_structure_event(df, swings, base_trend)

    # اگه آخرین رویداد ساختاری CHoCH خلاف جهت EMA بود، روند رو محتاطانه NEUTRAL می‌کنیم
    if event.type == "CHoCH" and event.direction != base_trend:
        trend = "NEUTRAL"
    else:
        trend = base_trend

    return TrendResult(trend=trend, ema_fast=ef, ema_slow=es, last_event=event, swings=swings)


def confirm_trend_1h(df: pd.DataFrame, higher_trend: str, fast: int = 20, slow: int = 50) -> TrendResult:
    """
    تأیید روند در 1H: هم‌جهتی EMA20/EMA50 + حجم بالاتر از میانگین + عدم CHoCH خلاف‌جهت.
    اگه higher_trend NEUTRAL باشه، تأیید معنی نداره (خروجی NEUTRAL).
    """
    if higher_trend not in ("BULLISH", "BEARISH"):
        return TrendResult("NEUTRAL", 0.0, 0.0, StructureEvent("NONE", "NONE"))

    ema_fast = ema(df["close"], fast)
    ema_slow = ema(df["close"], slow)
    ef, es = float(ema_fast.iloc[-1]), float(ema_slow.iloc[-1])

    ema_agrees = (ef > es) if higher_trend == "BULLISH" else (ef < es)

    vol_ma = df["volume"].rolling(20).mean()
    volume_ok = bool(df["volume"].iloc[-1] > vol_ma.iloc[-1]) if not pd.isna(vol_ma.iloc[-1]) else True

    swings = label_swings(find_swings(df))
    event = detect_last_structure_event(df, swings, higher_trend)
    choch_against = event.type == "CHoCH" and event.direction != higher_trend

    trend = higher_trend if (ema_agrees and volume_ok and not choch_against) else "NEUTRAL"
    return TrendResult(trend=trend, ema_fast=ef, ema_slow=es, last_event=event, swings=swings)


def has_bos_in_direction(df: pd.DataFrame, direction: str) -> bool:
    """برای تایم‌فریم M15: آیا اخیراً BOS/CHoCH هم‌جهت با direction رخ داده؟"""
    swings = label_swings(find_swings(df))
    event = detect_last_structure_event(df, swings, direction)
    return event.type in ("BOS", "CHoCH") and event.direction == direction
