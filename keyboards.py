from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import WEEKDAY_KEYS, now_local


def icon_button(text: str, callback_data: str, char: str, style: str | None = None) -> InlineKeyboardButton:
    kwargs = {"style": style} if style else {}
    return InlineKeyboardButton(text=f"{char}{text}", callback_data=callback_data, **kwargs)


def donate_link() -> str:
    return (
        '❤️<a href="https://www.sberbank.com/sms/pbpn?requisiteNumber=79950614483">'
        "Поддержать работу бота</a>"
    )


def menu_main(admin: bool = False) -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    m.row(icon_button("Расписание", "schedule", "🗓️"))
    m.row(icon_button("Звонки", "bell", "🔔"), icon_button("Рассылка", "mailing", "📣"))
    if admin:
        m.row(icon_button("Статистика", "admin_stats", "📊"))
    return m


def menu_days(show_stars: bool = False) -> InlineKeyboardMarkup:
    days = [
        ("Понедельник", "monday"), ("Вторник", "tuesday"), ("Среда", "wednesday"),
        ("Четверг", "thursday"), ("Пятница", "friday"), ("Суббота", "saturday"),
    ]
    today_key = WEEKDAY_KEYS[now_local().weekday()]
    m = InlineKeyboardMarkup()
    for i in range(0, 6, 3):
        row = [
            InlineKeyboardButton(name, callback_data=f"day_{key}", **({"style": "primary"} if key == today_key else {}))
            for name, key in days[i:i + 3]
        ]
        m.add(*row)
    if show_stars:
        m.row(icon_button("Поддержать звёздами", "ask_stars", "⭐️"))
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_calls() -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    m.add(
        InlineKeyboardButton("Понедельник", callback_data="monday_calls"),
        InlineKeyboardButton("Четверг", callback_data="thursday_calls"),
        InlineKeyboardButton("Другие дни", callback_data="other_calls"),
    )
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_mail(subscribed: bool) -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    if subscribed:
        m.row(icon_button("Отписаться", "unsub", "❌", style="danger"))
    else:
        m.row(icon_button("Подписаться", "sub", "✅", style="success"))
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_stats() -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    m.row(InlineKeyboardButton("👥Пользователи", callback_data="list_users"))
    m.row(InlineKeyboardButton("👥Подписчики", callback_data="list_subs"))
    m.row(InlineKeyboardButton("Меню", callback_data="main"))
    return m


def menu_pages(kind: str, page: int, total: int) -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("◀️", callback_data=f"{kind}_{page - 1}"))
    if page < total:
        buttons.append(InlineKeyboardButton("▶️", callback_data=f"{kind}_{page + 1}"))
    if buttons:
        m.row(*buttons)
    m.row(icon_button("Статистика", "admin_stats", "📊"))
    return m


def build_schedule_caption(day_name: str, link: str, show_donate: bool) -> str:
    caption = f'📚Расписание на {day_name}\n📎<a href="{link}">Ссылка на расписание</a>'
    if show_donate:
        caption += f"\n\n{donate_link()}"
    return caption


def build_broadcast_caption(day_name: str, link: str) -> str:
    return f'📣Расписание на {day_name}\n📎<a href="{link}">Ссылка на расписание</a>\n\n{donate_link()}'


def format_stats_text(total: int, subs: int, daily: int) -> str:
    return f"📊Статистика:\n\nВсего: {total}\nПодписаны: {subs}\nСегодня: {daily}"
