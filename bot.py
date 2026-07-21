"""
ربات تلگرامی سیگنال‌دهی کریپتو
- اسکن کل بازار Bybit (جفت‌های USDT) بر اساس حجم معاملات
- تحلیل روند در 1H و 4H (EMA9/21, RSI14, MACD)
- برای نمادهایی که روند 1H و 4H هم‌جهت هستن، اجرای استراتژی ورود در M15
  (EMA9/21 + RSI14 + MACD + Bollinger Bands + VWAP + SuperTrend)
- ارسال نتیجه به تلگرام، هم به‌صورت خودکار (زمان‌بندی‌شده) و هم با دستور /scan

نکته مهم درباره‌ی فرمت پیام:
از HTML parse mode استفاده می‌کنیم نه Markdown، چون Markdown (نسخه قدیمی تلگرام)
نسبت به کاراکترهای تک _ * ` بدون جفت شدن خیلی حساسه و باعث BadRequest و سکوت
کامل ربات می‌شه. HTML فقط با < > & مشکل داره که اینجا escape می‌کنیم.
"""

import html
import logging
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from exchange_client import get_top_symbols_by_volume, get_klines
from strategy import analyze_symbol

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("crypto_signal_bot")


def run_market_scan() -> str:
    """اسکن بازار رو انجام می‌ده و متن نهایی پیام تلگرام رو برمی‌گردونه"""
    log.info("Starting market scan (top %s symbols by volume)...", config.TOP_N_SYMBOLS)
    symbols = get_top_symbols_by_volume(
        limit=config.TOP_N_SYMBOLS, min_quote_volume=config.MIN_QUOTE_VOLUME
    )

    buy_signals = []
    sell_signals = []
    aligned_bullish_wait = []
    aligned_bearish_wait = []
    errors = 0

    for symbol in symbols:
        try:
            df_4h = get_klines(symbol, "4h", limit=100)
            df_1h = get_klines(symbol, "1h", limit=100)
            df_15m = get_klines(symbol, "15m", limit=100)

            if len(df_4h) < 30 or len(df_1h) < 30 or len(df_15m) < 30:
                continue

            result = analyze_symbol(symbol, df_4h, df_1h, df_15m)
            m15 = result["m15"]

            if m15.signal == "BUY":
                buy_signals.append((symbol, result))
            elif m15.signal == "SELL":
                sell_signals.append((symbol, result))
            elif result["aligned"] and result["bias"] == "BULLISH":
                aligned_bullish_wait.append(symbol)
            elif result["aligned"] and result["bias"] == "BEARISH":
                aligned_bearish_wait.append(symbol)

            time.sleep(config.REQUEST_DELAY_SECONDS)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log.warning("Error analyzing %s: %s", symbol, exc)
            continue

    return format_report(
        symbols_count=len(symbols),
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        aligned_bullish_wait=aligned_bullish_wait,
        aligned_bearish_wait=aligned_bearish_wait,
        errors=errors,
    )


def _fmt_signal_line(symbol: str, m15) -> str:
    sym = html.escape(symbol)
    base = f"• <code>{sym}</code> — ورود: {m15.entry:.6g} | SL: {m15.stop_loss:.6g} | TP: {m15.take_profit:.6g}"
    if m15.rr:
        base += f" | R:R≈{m15.rr:.2f}"
    return base


def format_report(symbols_count, buy_signals, sell_signals, aligned_bullish_wait, aligned_bearish_wait, errors) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 <b>گزارش اسکن بازار</b> — {now}",
        f"نمادهای بررسی‌شده: {symbols_count} | خطا: {errors}",
        "",
    ]

    if buy_signals:
        lines.append("🟢 <b>سیگنال‌های BUY (M15، هم‌جهت با 1H/4H)</b>")
        for symbol, r in buy_signals[:15]:
            lines.append(_fmt_signal_line(symbol, r["m15"]))
        lines.append("")

    if sell_signals:
        lines.append("🔴 <b>سیگنال‌های SELL (M15، هم‌جهت با 1H/4H)</b>")
        for symbol, r in sell_signals[:15]:
            lines.append(_fmt_signal_line(symbol, r["m15"]))
        lines.append("")

    if not buy_signals and not sell_signals:
        lines.append("در حال حاضر هیچ سیگنال ورود کامل (M15) فعال نیست.\n")

    if aligned_bullish_wait:
        names = html.escape(", ".join(aligned_bullish_wait[:20]))
        lines.append(f"🟡 روند صعودی همسو (1H+4H) ولی M15 هنوز آماده نیست: {names}")
    if aligned_bearish_wait:
        names = html.escape(", ".join(aligned_bearish_wait[:20]))
        lines.append(f"🟡 روند نزولی همسو (1H+4H) ولی M15 هنوز آماده نیست: {names}")

    lines.append("\n⚠️ این پیام تحلیل خودکار است، نه توصیه‌ی مالی. مدیریت ریسک با خودتونه.")
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (
        "سلام! ✅ ربات فعال شد.\n\n"
        f"chat id شما: <code>{chat_id}</code>\n\n"
        "برای اینکه گزارش‌های خودکار برات ارسال بشه، این عدد رو در متغیر محیطی "
        "<code>TELEGRAM_CHAT_ID</code> روی Railway ست کن و سرویس رو Restart کن.\n\n"
        "دستورات:\n"
        "/scan — اسکن فوری بازار\n"
        "/help — راهنما"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "این ربات کل بازار Bybit (جفت‌های USDT پرحجم) رو اسکن می‌کنه:\n"
        "۱. روند 1H و 4H رو با EMA9/21 + RSI14 + MACD می‌سنجه\n"
        "۲. اگه هم‌جهت بودن، روی M15 با EMA/RSI/MACD/Bollinger/VWAP/SuperTrend سیگنال ورود می‌سازه\n"
        "۳. هر چند دقیقه یک‌بار خودکار اسکن می‌کنه و هم با دستور /scan دستی\n\n"
        "⚠️ صرفاً ابزار تحلیل خودکار است و توصیه‌ی مالی محسوب نمی‌شه."
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ در حال اسکن بازار... (ممکنه چند ده ثانیه طول بکشه)")
    try:
        report = run_market_scan()
    except Exception as exc:  # noqa: BLE001
        log.exception("scan failed")
        await update.message.reply_text(f"❌ خطا در اسکن: {exc}")
        return
    await send_long_message(update.effective_chat.id, context, report)


async def send_long_message(chat_id, context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    تلگرام پیام رو تا حدود ۴۰۹۶ کاراکتر قبول می‌کنه؛ در صورت نیاز تکه‌تکه می‌کنیم.
    اگه به هر دلیلی HTML پارس نشد (مثلاً کاراکتر غیرمنتظره)، به‌جای سکوت کامل،
    به‌صورت plain text دوباره ارسال می‌کنیم تا پیام حتماً به دست کاربر برسه.
    """
    limit = 3800
    for i in range(0, len(text), limit):
        chunk = text[i : i + limit]
        try:
            await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
        except BadRequest as exc:
            log.warning("HTML parse failed (%s), sending as plain text instead", exc)
            await context.bot.send_message(chat_id=chat_id, text=chunk)


async def scheduled_scan_job(context: ContextTypes.DEFAULT_TYPE):
    if not config.TELEGRAM_CHAT_ID:
        log.info("TELEGRAM_CHAT_ID تنظیم نشده؛ از /start استفاده کن و متغیر محیطی رو ست کن.")
        return
    try:
        report = run_market_scan()
        await send_long_message(config.TELEGRAM_CHAT_ID, context, report)
    except Exception:  # noqa: BLE001
        log.exception("scheduled scan failed")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled exception while processing update: %s", context.error, exc_info=context.error)


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN تنظیم نشده. متغیر محیطی رو ست کن.")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_error_handler(on_error)

    app.job_queue.run_repeating(
        scheduled_scan_job,
        interval=config.SCAN_INTERVAL_MINUTES * 60,
        first=30,
    )

    log.info("Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
