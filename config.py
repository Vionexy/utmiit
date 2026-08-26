from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_SITE_PATH = os.getenv("GITHUB_SITE_PATH", "schedule")
GITHUB_ENABLED = bool(GITHUB_TOKEN and GITHUB_REPO)
GITHUB_API = "https://api.github.com"

DB_PATH = os.getenv("DB_PATH", "subscribers.db")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3

# Кемерово, UTC+7, без переходов на летнее время
LOCAL_TZ = timezone(timedelta(hours=7), "Кемерово")


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def today_local() -> str:
    """Дата по Кемерову - по ней считаются посещения за сегодня."""
    return now_local().strftime("%Y-%m-%d")


def github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "utmiitbot",
    }


class ConfigError(RuntimeError):
    pass


def validate() -> None:
    missing = [
        name for name, value in (("BOT_TOKEN", API_TOKEN), ("ADMIN_ID", ADMIN_ID)) if not value
    ]
    if missing:
        raise ConfigError(f"не заданы переменные окружения: {', '.join(missing)}")


SCHEDULE_FILES = {
    "monday":    {"id": "1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK", "name": "понедельник",
                  "link": "https://drive.google.com/file/d/1d7xrNLd8qpde_5jLvBdJjG9e3eOsjohK/view"},
    "tuesday":   {"id": "1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ", "name": "вторник",
                  "link": "https://drive.google.com/file/d/1qHNHC7uwXdECuEMfDoPiuv5bX0Ip0OpQ/view"},
    "wednesday": {"id": "1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA", "name": "среду",
                  "link": "https://drive.google.com/file/d/1hWMqMdeU2rcrNMx4jbOCr5ofGixsIJwA/view"},
    "thursday":  {"id": "1O649rLM_VuBO31VF49noXfp1Evr-XfCN", "name": "четверг",
                  "link": "https://drive.google.com/file/d/1O649rLM_VuBO31VF49noXfp1Evr-XfCN/view"},
    "friday":    {"id": "1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW", "name": "пятницу",
                  "link": "https://drive.google.com/file/d/1YmQGiirdBryJlI3tx0SdU-g1gGm-6AaW/view"},
    "saturday":  {"id": "1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex", "name": "субботу",
                  "link": "https://drive.google.com/file/d/1hkXSDN-Dz86QGeyjhLZ7jlvSd9sMwmex/view"},
}

DAY_MAP = {
    "пн": "monday",    "понедельник": "monday",
    "вт": "tuesday",   "вторник": "tuesday",
    "ср": "wednesday", "среда": "wednesday",
    "чт": "thursday",  "четверг": "thursday",
    "пт": "friday",    "пятница": "friday",
    "сб": "saturday",  "суббота": "saturday",
    "все": "all",
}

DAY_TITLES = {
    "monday": "Понедельник", "tuesday": "Вторник", "wednesday": "Среда",
    "thursday": "Четверг", "friday": "Пятница", "saturday": "Суббота",
}

DAY_NAMES_SHORT = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср",
    "thursday": "Чт", "friday": "Пт", "saturday": "Сб",
}

WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CALLS = {
    "monday": """<b>Понедельник</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

🕐 <b>Классные часы:</b> 12:30–13:00

<b>3⃣</b> 13:05–13:50 | 13:55–14:40

<b>4⃣</b> 14:45–15:30 | 15:35–16:20""",

    "thursday": """<b>Четверг</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

<b>3⃣</b> 12:30–13:15 | 13:20–14:05

<b>4⃣</b> 14:10–14:55 | 15:00–15:45

🕐 <b>Классные часы (1 курс):</b> 15:50–16:20""",

    "other": """<b>Другие дни</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:40

<b>3⃣</b> 12:40–13:25 | 13:30–14:15

<b>4⃣</b> 14:25–15:10 | 15:15–16:00

<b>5⃣</b> 16:05–16:50 | 16:55–17:40""",
}

CALLS_TITLES = {"monday": "Понедельник", "thursday": "Четверг", "other": "Другие дни"}

PAGE_SIZE = 50
CACHE_TTL = 3600
CACHE_MAX_DAYS = 2
RENDER_DPI = 200
DONATE_EVERY = 4
VIEW_COUNTER_MAX = 5000

CHECK_INTERVAL_SEC = 900
CHECK_ERROR_RETRY_SEC = 60
INTERACTIONS_KEEP_DAYS = 90

SEND_CONCURRENCY = 20
SEND_RATE_PER_SEC = 25  # запас от лимита Telegram ~30 msg/sec
SEND_MAX_RETRIES = 3

THROTTLE_RATE_SEC = 0.7
THROTTLE_BURST = 5

TRACK_FLUSH_INTERVAL_SEC = 5
TRACK_QUEUE_MAX = 10_000

MEDIA_GROUP_LIMIT = 10
MAX_MESSAGE_LEN = 4000

STARS_MIN = 1
STARS_MAX = 10000
