"""
کلاینت داده‌ی بازار از Bybit (API عمومی v5، بدون نیاز به API Key)

چرا Bybit به‌جای Binance؟
Binance درخواست‌های سرورهای دیتاسنتری (Railway, AWS, GCP, ...) رو با خطای
HTTP 451 (Unavailable For Legal Reasons) بلاک می‌کنه — این محدودیت روی
رنج IP هاست‌هاست، نه یک کشور خاص، پس عوض کردن ریجن Railway هم حلش نمی‌کنه.
Bybit این محدودیت رو در سطح دیتای عمومی بازار نداره.
"""

import time
import logging
from typing import List, Optional

import requests
import pandas as pd

log = logging.getLogger(__name__)

BASE_URL = "https://api.bybit.com"
KLINE_ENDPOINT = "/v5/market/kline"
INSTRUMENTS_ENDPOINT = "/v5/market/instruments-info"
TICKERS_ENDPOINT = "/v5/market/tickers"

# نگاشت تایم‌فریم‌های متعارف به فرمت Bybit
INTERVAL_MAP = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}

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
                log.warning("Rate limited by Bybit, sleeping %s sec", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {data.get('retMsg')}")
            return data["result"]
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Bybit request failed for {path}: {last_exc}")


def get_usdt_symbols() -> List[str]:
    """لیست همه‌ی جفت‌ارزهای اسپات فعال با quote=USDT"""
    result = _get(INSTRUMENTS_ENDPOINT, params={"category": "spot"})
    symbols = []
    for s in result.get("list", []):
        if s.get("quoteCoin") == "USDT" and s.get("status") == "Trading":
            symbols.append(s["symbol"])
    return symbols


def get_top_symbols_by_volume(limit: int = 40, min_quote_volume: float = 0) -> List[str]:
    """
    همه‌ی جفت‌های USDT رو بر اساس حجم ۲۴ ساعته مرتب می‌کنه و N تای برتر رو برمی‌گردونه
    (اسکن هزاران نماد در هر چرخه عملی نیست و به Rate Limit می‌خوره).
    """
    usdt_symbols = set(get_usdt_symbols())
    result = _get(TICKERS_ENDPOINT, params={"category": "spot"})
    tickers = result.get("list", [])
    filtered = [
        t for t in tickers
        if t["symbol"] in usdt_symbols and float(t.get("turnover24h", 0) or 0) >= min_quote_volume
    ]
    filtered.sort(key=lambda t: float(t.get("turnover24h", 0) or 0), reverse=True)
    return [t["symbol"] for t in filtered[:limit]]


def get_klines(symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
    """
    interval یکی از: 15m, 1h, 4h, 1d
    خروجی: DataFrame با ستون‌های timestamp, open, high, low, close, volume (قدیمی‌ترین تا جدیدترین)
    """
    bybit_interval = INTERVAL_MAP.get(interval, interval)
    result = _get(
        KLINE_ENDPOINT,
        params={"category": "spot", "symbol": symbol, "interval": bybit_interval, "limit": limit},
    )
    rows = result.get("list", [])
    # Bybit جدیدترین کندل رو اول می‌ده؛ باید معکوس بشه تا زمانی صعودی باشه
    rows = list(reversed(rows))
    cols = ["open_time", "open", "high", "low", "close", "volume", "turnover"]
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]
