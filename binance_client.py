"""
کلاینت ساده برای Binance Public REST API
نکته مهم: برای دیتای بازار (قیمت/کندل) نیازی به API Key نیست؛ این endpoint ها عمومی هستن.
"""

import time
import logging
from typing import List, Dict, Optional

import requests
import pandas as pd

log = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"
EXCHANGE_INFO_ENDPOINT = "/api/v3/exchangeInfo"
TICKER_24H_ENDPOINT = "/api/v3/ticker/24hr"

_session = requests.Session()
_session.headers.update({"User-Agent": "crypto-signal-bot/1.0"})


def _get(path: str, params: Optional[dict] = None, retries: int = 3, timeout: int = 10):
    url = BASE_URL + path
    last_exc = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                # rate limit -> صبر کن و دوباره امتحان کن
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning("Rate limited by Binance, sleeping %s sec", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Binance request failed for {path}: {last_exc}")


def get_usdt_symbols() -> List[str]:
    """لیست همه‌ی جفت‌ارزهای اسپات فعال با quote=USDT"""
    data = _get(EXCHANGE_INFO_ENDPOINT)
    symbols = []
    for s in data.get("symbols", []):
        if (
            s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed", True)
        ):
            symbols.append(s["symbol"])
    return symbols


def get_top_symbols_by_volume(limit: int = 40, min_quote_volume: float = 0) -> List[str]:
    """
    برای اسکن کل بازار به‌صورت عملی: همه‌ی جفت‌های USDT رو بر اساس حجم ۲۴ ساعته
    مرتب می‌کنه و N تای برتر رو برمی‌گردونه (چون واکشی کندل برای هزاران نماد
    در هر چرخه عملی نیست و به Rate Limit می‌خوره).
    """
    usdt_symbols = set(get_usdt_symbols())
    tickers = _get(TICKER_24H_ENDPOINT)
    filtered = [
        t for t in tickers
        if t["symbol"] in usdt_symbols and float(t.get("quoteVolume", 0)) >= min_quote_volume
    ]
    filtered.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
    return [t["symbol"] for t in filtered[:limit]]


def get_klines(symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
    """
    interval یکی از: 15m, 1h, 4h, 1d و ...
    خروجی: DataFrame با ستون‌های timestamp, open, high, low, close, volume
    """
    raw = _get(
        KLINES_ENDPOINT,
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]
