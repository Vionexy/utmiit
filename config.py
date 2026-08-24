from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_SITE_PATH = os.getenv("GITHUB_SITE_PATH", "schedule")
GITHUB_ENABLED = bool(GITHUB_TOKEN and GITHUB_REPO)
GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "utmiitbot",
}

DB_PATH = os.getenv("DB_PATH", "subscribers.db")

LOCAL_TZ = timezone(timedelta(hours=7))


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


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

DAY_NAMES_SHORT = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср",
    "thursday": "Чт", "friday": "Пт", "saturday": "Сб",
}

WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CALLS = {
    "monday_calls": """<b>Понедельник</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

🕐 <b>Классные часы:</b> 12:30–13:00

<b>3⃣</b> 13:05–13:50 | 13:55–14:40

<b>4⃣</b> 14:45–15:30 | 15:35–16:20""",

    "thursday_calls": """<b>Четверг</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:30

<b>3⃣</b> 12:30–13:15 | 13:20–14:05

<b>4⃣</b> 14:10–14:55 | 15:00–15:45

🕐 <b>Классные часы (1 курс):</b> 15:50–16:20""",

    "other_calls": """<b>Другие дни</b>

<b>1⃣</b> 8:30–9:15 | 9:20–10:05

<b>2⃣</b> 10:15–11:00
🍴 <b>Обед:</b> 11:00–11:15
<b>2⃣</b> 11:15–12:00

🍴 <b>Обед:</b> 12:00–12:40

<b>3⃣</b> 12:40–13:25 | 13:30–14:15

<b>4⃣</b> 14:25–15:10 | 15:15–16:00

<b>5⃣</b> 16:05–16:50 | 16:55–17:40""",
}

PAGE_SIZE = 50
CACHE_TTL = 3600
DONATE_EVERY = 4

CHECK_INTERVAL_SEC = 900
CHECK_ERROR_RETRY_SEC = 60

SEND_CONCURRENCY = 25
SEND_RATE_PER_SEC = 25  # запас от лимита Telegram ~30 msg/sec

STARS_MIN = 1
STARS_MAX = 10000
