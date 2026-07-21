import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# چند تا از پرحجم‌ترین جفت‌ارزهای USDT اسکن بشن (اسکن کل هزاران نماد در هر چرخه عملی نیست)
TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "40"))

# حداقل حجم معاملات ۲۴ ساعته (به دلار) برای ورود به اسکن — نمادهای کم‌حجم و نویزی رو فیلتر می‌کنه
MIN_QUOTE_VOLUME = float(os.getenv("MIN_QUOTE_VOLUME", "5000000"))

# هر چند دقیقه یک‌بار اسکن خودکار انجام بشه
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

# فاصله بین درخواست‌های متوالی به Binance (برای رعایت Rate Limit)
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "0.15"))
