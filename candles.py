"""
ماژول مستقل: تشخیص کندل‌های تأییدی ورود
مجاز: Bullish Engulfing, Bearish Engulfing, Pin Bar
"""

import pandas as pd


def is_bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    prev_bearish = prev["close"] < prev["open"]
    last_bullish = last["close"] > last["open"]
    engulfs = last["close"] >= prev["open"] and last["open"] <= prev["close"]
    return bool(prev_bearish and last_bullish and engulfs)


def is_bearish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 2:
        return False
    prev, last = df.iloc[-2], df.iloc[-1]
    prev_bullish = prev["close"] > prev["open"]
    last_bearish = last["close"] < last["open"]
    engulfs = last["close"] <= prev["open"] and last["open"] >= prev["close"]
    return bool(prev_bullish and last_bearish and engulfs)


def is_pin_bar(df: pd.DataFrame, direction: str, min_wick_ratio: float = 0.6) -> bool:
    """
    Pin Bar صعودی: سایه‌ی پایینی بلند (رد شدن از قیمت‌های پایین‌تر) + بسته‌شدن نزدیک سقف کندل
    Pin Bar نزولی: برعکس
    """
    if len(df) < 1:
        return False
    last = df.iloc[-1]
    full_range = last["high"] - last["low"]
    if full_range == 0:
        return False

    body_top = max(last["open"], last["close"])
    body_bottom = min(last["open"], last["close"])
    lower_wick = body_bottom - last["low"]
    upper_wick = last["high"] - body_top

    if direction == "BULLISH":
        return bool((lower_wick / full_range) >= min_wick_ratio and last["close"] > body_bottom)
    if direction == "BEARISH":
        return bool((upper_wick / full_range) >= min_wick_ratio and last["close"] < body_top)
    return False


def has_confirmation_candle(df: pd.DataFrame, direction: str) -> bool:
    if direction == "BULLISH":
        return is_bullish_engulfing(df) or is_pin_bar(df, "BULLISH")
    if direction == "BEARISH":
        return is_bearish_engulfing(df) or is_pin_bar(df, "BEARISH")
    return False
