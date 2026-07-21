"""
کلاینت داده‌ی بازار از CryptoCompare (min-api.cryptocompare.com)

چرا CryptoCompare به‌جای API مستقیم صرافی‌ها (Binance/Bybit/...)؟
صرافی‌های متمرکز به‌خاطر الزامات رگولاتوری/KYC، درخواست‌های سرورهای
دیتاسنتری (Railway, AWS, GCP, ...) رو مسدود می‌کنن (خطای 451 یا 403) —
این مسدودسازی مخصوص یک صرافی نیست و روی همه‌شون دیده می‌شه.
CryptoCompare یک سرویس تجمیع‌کننده‌ی دیتاست (نه صرافی معامله‌گری)
و این محدودیت رو نداره، پس برای اجرا روی سرور ابری قابل‌اعتمادتره.

محدودیت مهم: برای «اسکن کل بازار» به‌صورت واقعی، نیاز به یک لیست
پویا و قابل‌اعتماد از نمادهای پرحجم داریم. چون endpoint های رتبه‌بندی
حجم در APIهای رایگان می‌تونن ناپایدار باشن، از یک لیست ثابت و
قابل‌ویرایش از کوین‌های اصلی بازار (COIN_UNIVERSE پایین همین فایل)
استفاده می‌کنیم که عملاً همون بخش مهم و پرحجم بازاره.
"""

import time
import logging
from typing import List, Optional

import requests
import pandas as pd

log = logging.getLogger(__name__)

BASE_URL = "https://min-api.cryptocompare.com"
HISTOHOUR_ENDPOINT = "/data/v2/histohour"
HISTOMINUTE_ENDPOINT = "/data/v2/histominute"

INTERVAL_CONFIG = {
    "15m": (HISTOMINUTE_ENDPOINT, 15),
    "1h": (HISTOHOUR_ENDPOINT, 1),
    "4h": (HISTOHOUR_ENDPOINT, 4),
}

# لیست کوین‌های اصلی و پرحجم بازار (base asset، همیشه در برابر USDT تحلیل می‌شن)
# می‌تونی هر کوینی که می‌خوای اسکن بشه رو اینجا اضافه/حذف کنی
COIN_UNIVERSE = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "MATIC", "LTC", "TRX", "ATOM", "UNI", "ETC", "XLM", "FIL", "APT", "ARB",
    "OP", "NEAR", "INJ", "SUI", "TON", "SHIB", "PEPE", "RENDER", "FTM", "AAVE",
    "ALGO", "VET", "ICP", "HBAR", "SAND", "MANA", "AXS", "GRT", "EOS", "XTZ",
]

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-signal-bot/1.0"})


def _get(path: str, params: Optional[dict] = None, retries: int = 3, timeout: int = 10):
    url = BASE_URL + path
    last_exc = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning("Rate limited by CryptoCompare, sleeping %s sec", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("Response") == "Error":
                raise RuntimeError(f"CryptoCompare API error: {data.get('Message')}")
            return data
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"CryptoCompare request failed for {path}: {last_exc}")


def get_usdt_symbols() -> List[str]:
    """لیست نمادهای قابل‌اسکن (به فرمت نمایشی مثل BTCUSDT)"""
    return [f"{coin}USDT" for coin in COIN_UNIVERSE]


def get_top_symbols_by_volume(limit: int = 40, min_quote_volume: float = 0) -> List[str]:
    """
    به‌جای رتبه‌بندی پویا (که به endpoint ناپایدار نیاز داره)، از لیست ثابت
    کوین‌های اصلی بازار استفاده می‌کنیم. این لیست همون بخش پرحجم و مهم
    بازار رو پوشش می‌ده. پارامتر min_quote_volume فعلاً استفاده نمی‌شه
    (برای سازگاری با بقیه‌ی کد نگه داشته شده).
    """
    symbols = get_usdt_symbols()
    return symbols[:limit]


def get_klines(symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
    """
    symbol به فرمت نمایشی مثل 'BTCUSDT' — خودش base رو استخراج می‌کنه.
    interval یکی از: 15m, 1h, 4h
    خروجی: DataFrame با ستون‌های timestamp, open, high, low, close, volume
    """
    if not symbol.endswith("USDT"):
        raise ValueError(f"نماد {symbol} با فرمت مورد انتظار (ختم به USDT) مطابقت نداره")
    base = symbol[: -len("USDT")]

    endpoint, aggregate = INTERVAL_CONFIG.get(interval, (HISTOHOUR_ENDPOINT, 1))
    data = _get(
        endpoint,
        params={"fsym": base, "tsym": "USDT", "limit": limit, "aggregate": aggregate},
    )
    rows = data.get("Data", {}).get("Data", [])
    if not rows:
        raise RuntimeError(f"دیتای کندل خالی برای {symbol} ({interval})")

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"volumefrom": "volume"})
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]
