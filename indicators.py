"""
ماژول محاسبه اندیکاتورهای تکنیکال
همه‌ی توابع روی pandas.Series / DataFrame کار می‌کنن و وابستگی خارجی جز pandas/numpy ندارن
(عمداً از کتابخانه‌ی ta استفاده نشده تا نصب روی Railway ساده‌تر و بدون مشکل نسخه باشه)
"""

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # میانگین‌گیری به روش Wilder (همون چیزی که RSI استاندارد استفاده می‌کنه)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = sma(series, period)
    std = series.rolling(window=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """
    خروجی: (direction, line)
    direction: 1 = صعودی (سبز) / -1 = نزولی (قرمز) برای هر ردیف
    line: مقدار خط SuperTrend
    """
    hl2 = (df["high"] + df["low"]) / 2
    atr_val = atr(df, period)
    upper_band = hl2 + multiplier * atr_val
    lower_band = hl2 - multiplier * atr_val

    direction = pd.Series(index=df.index, dtype="int64")
    line = pd.Series(index=df.index, dtype="float64")

    final_upper = upper_band.copy()
    final_lower = lower_band.copy()

    for i in range(len(df)):
        if i == 0:
            direction.iloc[i] = 1
            line.iloc[i] = lower_band.iloc[i]
            continue

        prev_final_upper = final_upper.iloc[i - 1]
        prev_final_lower = final_lower.iloc[i - 1]

        # تا وقتی ATR هنوز مقدار معتبر نداره (دوره‌ی گرم‌کردن)، مقدار خام باند رو نگه دار
        if pd.isna(prev_final_upper):
            final_upper.iloc[i] = upper_band.iloc[i]
        elif upper_band.iloc[i] < prev_final_upper or df["close"].iloc[i - 1] > prev_final_upper:
            final_upper.iloc[i] = upper_band.iloc[i]
        else:
            final_upper.iloc[i] = prev_final_upper

        if pd.isna(prev_final_lower):
            final_lower.iloc[i] = lower_band.iloc[i]
        elif lower_band.iloc[i] > prev_final_lower or df["close"].iloc[i - 1] < prev_final_lower:
            final_lower.iloc[i] = lower_band.iloc[i]
        else:
            final_lower.iloc[i] = prev_final_lower

        prev_direction = direction.iloc[i - 1]
        close_now = df["close"].iloc[i]

        if pd.isna(final_lower.iloc[i]) or pd.isna(final_upper.iloc[i]):
            direction.iloc[i] = prev_direction
        elif prev_direction == 1:
            direction.iloc[i] = -1 if close_now < final_lower.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if close_now > final_upper.iloc[i] else -1

        line.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return direction, line


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """
    VWAP بر مبنای سشن روزانه (UTC) - هر روز از صفر شروع می‌شه.
    df باید ستون 'timestamp' (datetime, UTC) داشته باشه.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical_price * df["volume"]
    day = df["timestamp"].dt.date
    cum_tp_vol = tp_vol.groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)
