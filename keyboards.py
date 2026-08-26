from __future__ import annotations

from telebot.callback_data import CallbackData
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import CALLS_TITLES, DAY_TITLES, MAX_MESSAGE_LEN, WEEKDAY_KEYS, now_local
from db import Stats, UserRecord

DAY_CB = CallbackData("day", prefix="day")
CALLS_CB = CallbackData("kind", prefix="calls")
PAGE_CB = CallbackData("kind", "page", prefix="page")

MENU = "menu"
SCHEDULE = "schedule"
BELL = "bell"
MAILING = "mailing"
SUB = "sub"
UNSUB = "unsub"
ADMIN_STATS = "admin_stats"
ASK_STARS = "ask_stars"
SEND_CONFIRM = "send_yes"
SEND_CANCEL = "send_no"
NOOP = "noop"

DONATE_URL = "https://www.sberbank.com/sms/pbpn?requisiteNumber=79950614483"
DONATE_LINK = f'❤️<a href="{DONATE_URL}">Поддержать работу бота</a>'


def _button(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    # style понимают не все клиенты, поэтому текст кнопки самодостаточный
    return InlineKeyboardButton(text, callback_data=data, **({"style": style} if style else {}))


def _menu_row() -> list[InlineKeyboardButton]:
    return [_button("Меню", MENU)]


def menu_main(is_admin: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(_button("🗓️Расписание", SCHEDULE, style="primary"))
    markup.row(_button("🔔Звонки", BELL), _button("📣Рассылка", MAILING))
    if is_admin:
        markup.row(_button("📊Статистика", ADMIN_STATS))
    return markup


def menu_days(show_stars: bool = False) -> InlineKeyboardMarkup:
    today = WEEKDAY_KEYS[now_local().weekday()]
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for key, title in DAY_TITLES.items():
        is_today = key == today
        buttons.append(_button(title, DAY_CB.new(day=key), style="primary" if is_today else None))
    markup.add(*buttons)
    if show_stars:
        markup.row(_button("⭐️Поддержать звёздами", ASK_STARS))
    markup.row(*_menu_row())
    return markup


def menu_calls(active: str | None = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        *(
            _button(title, CALLS_CB.new(kind=kind), style="primary" if kind == active else None)
            for kind, title in CALLS_TITLES.items()
        )
    )
    markup.row(*_menu_row())
    return markup


def menu_mail(subscribed: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if subscribed:
        markup.row(_button("❌Отписаться", UNSUB, style="danger"))
    else:
        markup.row(_button("✅Подписаться", SUB, style="success"))
    markup.row(*_menu_row())
    return markup


def menu_stats() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(_button("👥Пользователи", PAGE_CB.new(kind="users", page=1)))
    markup.row(_button("👥Подписчики", PAGE_CB.new(kind="subs", page=1)))
    markup.row(*_menu_row())
    return markup


def menu_pages(kind: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    nav = []
    if page > 1:
        nav.append(_button("◀️", PAGE_CB.new(kind=kind, page=page - 1)))
    nav.append(_button(f"{page}/{total_pages}", NOOP))
    if page < total_pages:
        nav.append(_button("▶️", PAGE_CB.new(kind=kind, page=page + 1)))
    markup.row(*nav)
    markup.row(_button("📊Статистика", ADMIN_STATS))
    markup.row(*_menu_row())
    return markup


def menu_send_confirm() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        _button("Отправить", SEND_CONFIRM, style="success"),
        _button("Отмена", SEND_CANCEL, style="danger"),
    )
    return markup


def schedule_caption(day_name: str, link: str, with_donate: bool) -> str:
    caption = f'📚Расписание на {day_name}\n📎<a href="{link}">Ссылка на расписание</a>'
    return f"{caption}\n\n{DONATE_LINK}" if with_donate else caption


def broadcast_caption(day_name: str, link: str) -> str:
    return (
        f'📣Расписание на {day_name}\n📎<a href="{link}">Ссылка на расписание</a>'
        f"\n\n{DONATE_LINK}"
    )


def stats_text(stats: Stats) -> str:
    return (
        "📊Статистика:\n\n"
        f"Всего: {stats.total}\n"
        f"Подписаны: {stats.subscribers}\n"
        f"Сегодня: {stats.daily}"
    )


def users_page_text(title: str, users: list[UserRecord], page: int, total_pages: int, total: int) -> str:
    header = f"👥{title} ({page}/{total_pages}):"
    if not users:
        return f"{header}\n\nПока никого."
    lines = [header, ""]
    length = len(header) + 1
    for user in users:
        row = user.display()
        if length + len(row) + 1 > MAX_MESSAGE_LEN:
            lines.append("…список обрезан, чтобы уложиться в лимит Telegram")
            break
        lines.append(row)
        length += len(row) + 1
    return "\n".join(lines)

