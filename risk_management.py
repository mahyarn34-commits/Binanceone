"""
ماژول مستقل: مدیریت ریسک

این ربات معامله رو خودش اجرا نمی‌کنه (فقط سیگنال می‌ده)، پس محدودیت‌های
«حداکثر ضرر روزانه» و «حداکثر ضررهای متوالی» فقط وقتی معنی دارن که کاربر
نتیجه‌ی معاملاتش رو به ربات گزارش بده. برای همین دستور /result در بات
اضافه شده (win/loss) تا این ماژول واقعاً کار کنه، نه فقط یک محاسبه‌ی ایستا.

State به‌صورت in-memory نگه داشته می‌شه (per chat_id) و هر روز UTC ریست می‌شه.
اگه ربات ری‌استارت بشه، state از صفر شروع می‌شه — برای پایداری کامل بین
ری‌استارت‌ها باید state رو توی دیتابیس/فایل ذخیره کرد (خارج از اسکوپ فعلی).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import config


@dataclass
class RiskState:
    date: str
    daily_pnl_percent: float = 0.0
    consecutive_losses: int = 0
    trades_logged: int = 0


_state: Dict[int, RiskState] = {}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_state(chat_id: int) -> RiskState:
    today = _today()
    st = _state.get(chat_id)
    if st is None or st.date != today:
        st = RiskState(date=today)
        _state[chat_id] = st
    return st


def can_trade(chat_id: int) -> "tuple[bool, str]":
    st = _get_state(chat_id)
    if st.daily_pnl_percent <= -abs(config.DAILY_MAX_LOSS_PERCENT):
        return False, f"به حداکثر ضرر مجاز امروز رسیدی ({st.daily_pnl_percent:.2f}%). امروز دیگه معامله نکن."
    if st.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
        return False, f"{st.consecutive_losses} ضرر متوالی داشتی. بهتره یه استراحت کوتاه بدی و ذهنیتت رو ریست کنی."
    return True, ""


def record_trade_result(chat_id: int, result: str, rr: Optional[float] = None) -> RiskState:
    """
    result: 'win' یا 'loss'
    برای win از rr (اگه داده بشه) استفاده می‌کنه، وگرنه از MIN_RISK_REWARD پیش‌فرض کانفیگ.
    """
    st = _get_state(chat_id)
    risk_pct = abs(config.RISK_PER_TRADE_PERCENT)

    if result == "win":
        gain = risk_pct * (rr if rr else config.MIN_RISK_REWARD)
        st.daily_pnl_percent += gain
        st.consecutive_losses = 0
    elif result == "loss":
        st.daily_pnl_percent -= risk_pct
        st.consecutive_losses += 1

    st.trades_logged += 1
    return st


def suggest_position_size(account_balance: float, entry: float, stop_loss: float) -> Optional[float]:
    """
    حجم پیشنهادی پوزیشن بر مبنای درصد ریسک ثابت هر معامله (config.RISK_PER_TRADE_PERCENT).
    خروجی: مقدار (quantity) بر حسب asset پایه.
    """
    if entry == stop_loss:
        return None
    risk_amount = account_balance * (abs(config.RISK_PER_TRADE_PERCENT) / 100)
    stop_distance = abs(entry - stop_loss)
    if stop_distance == 0:
        return None
    return round(risk_amount / stop_distance, 6)


def status_text(chat_id: int) -> str:
    st = _get_state(chat_id)
    ok, reason = can_trade(chat_id)
    lines = [
        f"📅 وضعیت ریسک امروز ({st.date}):",
        f"سود/زیان تجمعی: {st.daily_pnl_percent:+.2f}%",
        f"ضررهای متوالی: {st.consecutive_losses}",
        f"معاملات ثبت‌شده: {st.trades_logged}",
        f"وضعیت: {'✅ مجاز به معامله' if ok else '⛔ ' + reason}",
    ]
    return "\n".join(lines)
