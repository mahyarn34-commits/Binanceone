"""
ربات تلگرامی سیگنال‌دهی کریپتو
- اسکن کل بازار Binance (جفت‌های USDT) بر اساس حجم معاملات
- تحلیل روند در 1H و 4H (EMA9/21, RSI14, MACD)
- برای نمادهایی که روند 1H و 4H هم‌جهت هستن، اجرای استراتژی ورود در M15
  (EMA9/21 + RSI14 + MACD + Bollinger Bands + VWAP + SuperTrend)
- ارسال نتیجه به تلگرام، هم به‌صورت خودکار (زمان‌بندی‌شده) و هم با دستور /scan
"""

import logging
import os
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from binance_client import get_top_symbols_by_volume, get_klines
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


def format_report(symbols_count, buy_signals, sell_signals, aligned_bullish_wait, aligned_bearish_wait, errors) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 *گزارش اسکن بازار* — {now}", f"نمادهای بررسی‌شده: {symbols_count} | خطا: {errors}", ""]

    if buy_signals:
        lines.append("🟢 *سیگنال‌های BUY (M15، هم‌جهت با 1H/4H)*")
        for symbol, r in buy_signals[:15]:
            m15 = r["m15"]
            lines.append(
                f"• `{symbol}` — ورود: {m15.entry:.6g} | SL: {m15.stop_loss:.6g} | "
                f"TP: {m15.take_profit:.6g} | R:R≈{m15.rr:.2f}" if m15.rr else
                f"• `{symbol}` — ورود: {m15.entry:.6g} | SL: {m15.stop_loss:.6g} | TP: {m15.take_profit:.6g}"
            )
        lines.append("")

    if sell_signals:
        lines.append("🔴 *سیگنال‌های SELL (M15، هم‌جهت با 1H/4H)*")
        for symbol, r in sell_signals[:15]:
            m15 = r["m15"]
            lines.append(
                f"• `{symbol}` — ورود: {m15.entry:.6g} | SL: {m15.stop_loss:.6g} | "
                f"TP: {m15.take_profit:.6g} | R:R≈{m15.rr:.2f}" if m15.rr else
                f"• `{symbol}` — ورود: {m15.entry:.6g} | SL: {m15.stop_loss:.6g} | TP: {m15.take_profit:.6g}"
            )
        lines.append("")

    if not buy_signals and not sell_signals:
        lines.append("در حال حاضر هیچ سیگنال ورود کامل (M15) فعال نیست.\n")

    if aligned_bullish_wait:
        lines.append(f"🟡 روند صعودی همسو (1H+4H) ولی M15 هنوز آماده نیست: {', '.join(aligned_bullish_wait[:20])}")
    if aligned_bearish_wait:
        lines.append(f"🟡 روند نزولی همسو (1H+4H) ولی M15 هنوز آماده نیست: {', '.join(aligned_bearish_wait[:20])}")

    lines.append("\n⚠️ این پیام تحلیل خودکار است، نه توصیه‌ی مالی. مدیریت ریسک با خودتونه.")
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "سلام! ✅ ربات فعال شد.\n\n"
        f"chat_id شما: `{chat_id}`\n\n"
        "برای اینکه گزارش‌های خودکار برات ارسال بشه، این عدد رو در متغیر محیطی "
        "`TELEGRAM_CHAT_ID` روی Railway ست کن و ربات رو ری‌استارت کن.\n\n"
        "دستورات:\n"
        "/scan — اسکن فوری بازار\n"
        "/help — راهنما",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "این ربات کل بازار Binance (جفت‌های USDT پرحجم) رو اسکن می‌کنه:\n"
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
    """تلگرام پیام رو تا حدود ۴۰۹۶ کاراکتر قبول می‌کنه؛ در صورت نیاز تکه‌تکه می‌کنیم"""
    limit = 3800
    for i in range(0, len(text), limit):
        await context.bot.send_message(
            chat_id=chat_id, text=text[i : i + limit], parse_mode=ParseMode.MARKDOWN
        )


async def scheduled_scan_job(context: ContextTypes.DEFAULT_TYPE):
    if not config.TELEGRAM_CHAT_ID:
        log.info("TELEGRAM_CHAT_ID تنظیم نشده؛ از /start استفاده کن و متغیر محیطی رو ست کن.")
        return
    try:
        report = run_market_scan()
        await send_long_message(config.TELEGRAM_CHAT_ID, context, report)
    except Exception:  # noqa: BLE001
        log.exception("scheduled scan failed")


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN تنظیم نشده. متغیر محیطی رو ست کن.")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))

    app.job_queue.run_repeating(
        scheduled_scan_job,
        interval=config.SCAN_INTERVAL_MINUTES * 60,
        first=30,
    )

    log.info("Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
