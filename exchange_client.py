"""
کلاینت داده‌ی بازار از Toobit (https://api.toobit.com)

نکته: قبلاً از CryptoCompare استفاده می‌شد چون صرافی‌های مستقیم معمولاً
سرورهای دیتاسنتری (Railway/AWS/...) رو مسدود می‌کنن. اگه بعد از دیپلوی
با خطای پیوسته مواجه شدی (مثلاً 403/451)، یعنی Toobit هم همون محدودیت
رو داره — در اون صورت باید یا از یک پراکسی/VPS خارج از رنج مسدودشده
استفاده کرد، یا دوباره به یک دیتا-آگریگیتور (مثل CryptoCompare) برگشت.

اندپوینت‌های استفاده‌شده (همه Public، بدون نیاز به API Key):
- GET /api/v1/exchangeInfo   -> لیست نمادها و وضعیت TRADING
- GET /quote/v1/ticker/24hr  -> حجم ۲۴ساعته برای رتبه‌بندی نمادهای پرحجم
- GET /quote/v1/klines       -> کندل‌ها (فرمت آرایه‌ای، نه دیکشنری)

مستندات: https://api-docs.toobit.com/api/spot-market-data.html
"""

import time
import logging
from typing import List, Optional

import requests
import pandas as pd

log = logging.getLogger(__name__)

BASE_URL = "https://api.toobit.com"
EXCHANGE_INFO_ENDPOINT = "/api/v1/exchangeInfo"
TICKER_24H_ENDPOINT = "/quote/v1/ticker/24hr"
KLINES_ENDPOINT = "/quote/v1/klines"

# اینترول‌های Toobit دقیقاً با چیزی که تو کد استفاده می‌کنیم یکیه: 15m, 1h, 4h
VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1w", "1M"}

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-signal-bot/2.0"})


def _get(path: str, params: Optional[dict] = None, retries: int = 3, timeout: int = 10):
    url = BASE_URL + path
    last_exc = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                wait = 5
                reset = resp.headers.get("X-Api-Limit-Reset-Timestamp")
                if reset:
                    try:
                        wait = max(1, (int(reset) - int(time.time() * 1000)) / 1000)
                    except (ValueError, TypeError):
                        pass
                log.warning("Rate limited by Toobit, sleeping %.1f sec", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Toobit request failed for {path}: {last_exc}")


def get_usdt_symbols() -> List[str]:
    """لیست نمادهای اسپات فعال (status=TRADING) که به USDT ختم می‌شن"""
    data = _get(EXCHANGE_INFO_ENDPOINT)
    symbols = data.get("symbols", [])
    return [
        s["symbol"]
        for s in symbols
        if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"
    ]


def get_top_symbols_by_volume(limit: int = 40, min_quote_volume: float = 0) -> List[str]:
    """
    نمادهای فعال اسپات رو بر اساس حجم معاملات ۲۴ساعته (quote volume) رتبه‌بندی می‌کنه
    و N تای پرحجم‌تر رو برمی‌گردونه.
    """
    active_symbols = set(get_usdt_symbols())
    tickers = _get(TICKER_24H_ENDPOINT)
    if isinstance(tickers, dict):
        tickers = tickers.get("data", tickers.get("list", []))

    ranked = []
    for t in tickers:
        symbol = t.get("s")
        if symbol not in active_symbols:
            continue
        try:
            qv = float(t.get("qv", 0))
        except (TypeError, ValueError):
            continue
        if qv < min_quote_volume:
            continue
        ranked.append((symbol, qv))

    ranked.sort(key=lambda x: x[1], reverse=True)
    symbols = [s for s, _ in ranked[:limit]]

    if not symbols:
        # اگه به هر دلیلی رتبه‌بندی حجم شکست خورد، حداقل چند نماد اصلی رو برگردون تا ربات کامل نخوابه
        log.warning("Volume ranking از Toobit خالی برگشت؛ به لیست پایه fallback می‌کنیم")
        fallback = [s for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"] if s in active_symbols]
        return fallback[:limit]

    return symbols


def get_klines(symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
    """
    خروجی: DataFrame با ستون‌های timestamp, open, high, low, close, volume
    """
    if interval not in VALID_INTERVALS:
        raise ValueError(f"اینتروال نامعتبر: {interval}")

    rows = _get(
        KLINES_ENDPOINT,
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    if not rows:
        raise RuntimeError(f"دیتای کندل خالی برای {symbol} ({interval})")

    # فرمت هر ردیف: [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote]
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
        ][: len(rows[0])],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]
