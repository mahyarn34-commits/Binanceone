import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# چند تا از پرحجم‌ترین جفت‌ارزهای USDT اسکن بشن (اسکن کل هزاران نماد در هر چرخه عملی نیست)
TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "40"))

# حداقل حجم معاملات ۲۴ ساعته (به دلار) برای ورود به اسکن — نمادهای کم‌حجم و نویزی رو فیلتر می‌کنه
MIN_QUOTE_VOLUME = float(os.getenv("MIN_QUOTE_VOLUME", "5000000"))

# هر چند دقیقه یک‌بار اسکن خودکار انجام بشه
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

# فاصله بین درخواست‌های متوالی به Toobit (برای رعایت Rate Limit)
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "0.15"))

# --- سیستم امتیازدهی (Scoring System) ---
# حداقل امتیاز (از ۱۰۰) برای اینکه سیگنال ورود صادر بشه
SIGNAL_SCORE_THRESHOLD = int(os.getenv("SIGNAL_SCORE_THRESHOLD", "70"))

# --- مدیریت ریسک ---
# درصد ریسک هر معامله از کل سرمایه
RISK_PER_TRADE_PERCENT = float(os.getenv("RISK_PER_TRADE_PERCENT", "1.0"))

# حداکثر ضرر مجاز روزانه (درصد) — بعد از این حد، ربات هشدار توقف معامله می‌ده
DAILY_MAX_LOSS_PERCENT = float(os.getenv("DAILY_MAX_LOSS_PERCENT", "3.0"))

# حداکثر ضررهای متوالی مجاز قبل از هشدار توقف
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

# حداقل نسبت ریسک‌به‌ریوارد قابل قبول برای صدور سیگنال
MIN_RISK_REWARD = float(os.getenv("MIN_RISK_REWARD", "2.0"))

# موجودی فرضی حساب (برای پیشنهاد حجم پوزیشن در پیام سیگنال)
ACCOUNT_BALANCE_USDT = float(os.getenv("ACCOUNT_BALANCE_USDT", "1000"))
