"""
ماژول مستقل: تشخیص Liquidity

فقط اطلاعات برمی‌گردونه (Equal High/Low, Liquidity Sweep, Stop Hunt, Fake Breakout)
تصمیم‌گیری نهایی در strategy.py انجام می‌شه.
"""

from dataclasses import dataclass
from typing import List, Literal, Optional

import pandas as pd


@dataclass
class EqualLevel:
    price: float
    count: int
    kind: Literal["high", "low"]


@dataclass
class SweepResult:
    swept: bool
    direction: Literal["BULLISH", "BEARISH", "NONE"] = "NONE"
    swept_level: Optional[float] = None
    reason: str = ""


def detect_equal_levels(df: pd.DataFrame, lookback: int = 20, tolerance_pct: float = 0.001) -> List[EqualLevel]:
    """
    سطوحی که چند بار قیمت تقریباً به یک مقدار برخورد کرده (Equal High/Low) —
    این‌ها معمولاً محل تجمع استاپ‌لاس‌ها و لیکوییدیتی هستن.
    """
    recent = df.tail(lookback)
    levels: List[EqualLevel] = []

    for kind, col in (("high", "high"), ("low", "low")):
        values = recent[col].values
        used = [False] * len(values)
        for i in range(len(values)):
            if used[i]:
                continue
            group = [values[i]]
            used[i] = True
            for j in range(i + 1, len(values)):
                if used[j]:
                    continue
                if abs(values[j] - values[i]) / values[i] <= tolerance_pct:
                    group.append(values[j])
                    used[j] = True
            if len(group) >= 2:
                levels.append(EqualLevel(price=float(sum(group) / len(group)), count=len(group), kind=kind))

    return levels


def detect_liquidity_sweep(df: pd.DataFrame, direction: str, lookback: int = 20) -> SweepResult:
    """
    Liquidity Sweep (Stop Hunt):
    - برای BUY: قیمت زیر یک Swing Low اخیر می‌ره (سل‌سایدِ لیکوییدیتی رو می‌گیره)
      و بعد در همون کندل یا کندل بعدی برمی‌گرده بالای اون سطح می‌بنده (رد شدن/Rejection).
    - برای SELL: برعکس، بالای یک Swing High اخیر می‌زنه و برمی‌گرده پایین می‌بنده.
    """
    if len(df) < lookback + 2:
        return SweepResult(swept=False, reason="دیتای کافی برای تشخیص سوییپ نیست")

    recent = df.tail(lookback + 2).reset_index(drop=True)
    last = recent.iloc[-1]

    if direction == "BULLISH":
        prior = recent.iloc[:-1]
        swing_low = prior["low"].min()
        wicked_below = last["low"] < swing_low
        closed_back_above = last["close"] > swing_low
        if wicked_below and closed_back_above:
            return SweepResult(True, "BULLISH", float(swing_low), "سوییپ سل‌سایدِ لیکوییدیتی + برگشت به بالای سطح")
        return SweepResult(False, reason="هنوز سوییپ صعودی رخ نداده")

    if direction == "BEARISH":
        prior = recent.iloc[:-1]
        swing_high = prior["high"].max()
        wicked_above = last["high"] > swing_high
        closed_back_below = last["close"] < swing_high
        if wicked_above and closed_back_below:
            return SweepResult(True, "BEARISH", float(swing_high), "سوییپ بای‌سایدِ لیکوییدیتی + برگشت به زیر سطح")
        return SweepResult(False, reason="هنوز سوییپ نزولی رخ نداده")

    return SweepResult(False, reason="جهت نامعتبر")


def detect_fake_breakout(df: pd.DataFrame, lookback: int = 20) -> bool:
    """
    Fake Breakout: کندل با بدنه‌ی کوچیک و سایه‌ی بلند که خارج از رنج اخیر باز/بسته نشده
    ولی wick بیرون از رنج زده — نشونه‌ی ضعف حرکت و احتمال برگشت.
    """
    if len(df) < lookback + 1:
        return False
    recent = df.tail(lookback + 1)
    prior_high = recent["high"].iloc[:-1].max()
    prior_low = recent["low"].iloc[:-1].min()
    last = recent.iloc[-1]

    body = abs(last["close"] - last["open"])
    full_range = last["high"] - last["low"]
    if full_range == 0:
        return False
    small_body = body / full_range < 0.35

    poked_above = last["high"] > prior_high and last["close"] < prior_high
    poked_below = last["low"] < prior_low and last["close"] > prior_low

    return bool(small_body and (poked_above or poked_below))
