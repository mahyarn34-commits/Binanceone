"""
ماژول مستقل: تشخیص خودکار محدوده‌های Supply & Demand

منطق: قبل از یک حرکت قوی (کندل/کندل‌های با رنج بزرگ نسبت به ATR)، معمولاً
چند کندل با رنج کوچیک (تجمع/Consolidation) وجود داره. اون محدوده‌ی تجمع
همون Base ای هست که به‌عنوان Zone معرفی می‌شه:
- حرکت قوی صعودی بعد از تجمع  -> محدوده‌ی تجمع = Demand Zone
- حرکت قوی نزولی بعد از تجمع  -> محدوده‌ی تجمع = Supply Zone

این ماژول فقط لیست Zoneها رو برمی‌گردونه؛ تصمیم نهایی (اینکه قیمت الان
داخل Zone هست یا نه و آیا باید وارد شد) در strategy.py گرفته می‌شه.
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

import pandas as pd

from indicators import atr


@dataclass
class Zone:
    kind: Literal["demand", "supply"]
    price_low: float
    price_high: float
    formed_index: int


def find_zones(df: pd.DataFrame, lookback: int = 60, base_max_candles: int = 3,
                impulse_atr_mult: float = 1.5) -> List[Zone]:
    if len(df) < lookback:
        lookback = len(df)
    recent = df.tail(lookback).reset_index(drop=True)
    atr_series = atr(recent, 14)

    zones: List[Zone] = []

    for i in range(base_max_candles, len(recent)):
        a = atr_series.iloc[i]
        if pd.isna(a) or a == 0:
            continue

        impulse = recent.iloc[i]
        impulse_range = impulse["high"] - impulse["low"]
        if impulse_range < impulse_atr_mult * a:
            continue

        is_bullish_impulse = impulse["close"] > impulse["open"]
        is_bearish_impulse = impulse["close"] < impulse["open"]
        if not (is_bullish_impulse or is_bearish_impulse):
            continue

        # به‌دنبال یک Base (۱ تا base_max_candles کندل با رنج کوچیک) درست قبل از این کندل ضربه‌ای
        base_candles = []
        for j in range(i - 1, max(i - 1 - base_max_candles, -1), -1):
            candle = recent.iloc[j]
            candle_range = candle["high"] - candle["low"]
            if candle_range <= a:
                base_candles.append(candle)
            else:
                break
        if not base_candles:
            continue

        base_low = min(c["low"] for c in base_candles)
        base_high = max(c["high"] for c in base_candles)
        formed_index = i - len(base_candles)

        if is_bullish_impulse:
            zones.append(Zone("demand", base_low, base_high, formed_index))
        else:
            zones.append(Zone("supply", base_low, base_high, formed_index))

    return zones


def price_in_zone(price: float, zones: List[Zone], direction: str) -> Optional[Zone]:
    """نزدیک‌ترین Zone هم‌جهت که قیمت فعلی داخلش قرار داره رو برمی‌گردونه (یا None)"""
    wanted_kind = "demand" if direction == "BULLISH" else "supply"
    matches = [z for z in zones if z.kind == wanted_kind and z.price_low <= price <= z.price_high]
    if not matches:
        return None
    return max(matches, key=lambda z: z.formed_index)
