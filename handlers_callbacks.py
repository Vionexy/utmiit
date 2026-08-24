from __future__ import annotations

import logging

from app_context import app, bot
from config import ADMIN_ID, CALLS, PAGE_SIZE, SCHEDULE_FILES
from keyboards import build_schedule_caption, format_stats_text, menu_calls, menu_days, menu_main, menu_mail, menu_pages, menu_stats
from media import send_photo_series
from middleware import track_user

logger = logging.getLogger(__name__)


async def _edit(call, text, markup=None):
    await bot.edit_message_text(
        chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=text, parse_mode="HTML", reply_markup=markup,
    )


def _require_admin(call) -> bool:
    return call.message.chat.id == ADMIN_ID


async def handle_admin_stats(call):
    if not _require_admin(call):
        await bot.answer_callback_query(call.id, "нет")
        return
    total, subs, daily = await app.db.get_stats()
    await _edit(call, format_stats_text(total, subs, daily), menu_stats())


async def _paged_list(call, kind: str, fetch_fn, state_key: str, page: int):
    state = app.state.get(call.message.chat.id)
    if page == 1 or state_key not in state:
        items = await fetch_fn()
        state[state_key] = items
        app.state.set(call.message.chat.id, state)
    items = app.state.get(call.message.chat.id).get(state_key, [])
    pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE or 1
    start = (page - 1) * PAGE_SIZE
    chunk = items[start:start + PAGE_SIZE]
    label = "Пользователи" if kind == "list_users" else "Подписчики"
    await _edit(call, f"👥{label} ({page}/{pages}):\n\n" + "\n".join(chunk), menu_pages(kind, page, pages))


async def handle_list_users(call):
    if not _require_admin(call):
        return
    page = 1 if call.data == "list_users" else int(call.data.rsplit("_", 1)[-1])
    await _paged_list(call, "list_users", app.db.get_users_list, "ul", page)


async def handle_list_subs(call):
    if not _require_admin(call):
        return
    page = 1 if call.data == "list_subs" else int(call.data.rsplit("_", 1)[-1])
    await _paged_list(call, "list_subs", app.db.get_subscribers_list, "sl", page)


async def handle_send_yes(call):
    if not _require_admin(call):
        return
    state = app.state.get(call.message.chat.id)
    text = state.get("text")
    users = state.get("users", [])
    await _edit(call, "📣...")
    ok, err = await app.broadcaster.mass_send_text(users, text)
    await bot.send_message(call.message.chat.id, f"✅Готово\nОтправлено: {ok}\nОшибок: {err}", parse_mode="HTML")
    app.state.pop(call.message.chat.id)


async def handle_send_no(call):
    await _edit(call, "❌Отменено")
    app.state.pop(call.message.chat.id)


async def handle_schedule(call):
    await _edit(call, "Выберите день👇", menu_days())


async def handle_mailing(call):
    subscribed = await app.db.check_sub(call.message.chat.id)
    text = "Вы подписаны✅" if subscribed else "Вы не подписаны"
    await _edit(call, text, menu_mail(subscribed))


async def handle_calls_entry(call):
    await _edit(call, CALLS[call.data], menu_calls())


async def handle_bell(call):
    await _edit(call, "Информация о звонках🔔", menu_calls())


async def handle_sub(call):
    await app.db.add_sub(call.message.chat.id)
    await _edit(call, "Вы подписаны✅", menu_mail(True))


async def handle_unsub(call):
    await app.db.del_sub(call.message.chat.id)
    await _edit(call, "Вы не подписаны", menu_mail(False))


async def handle_main(call):
    admin = call.message.chat.id == ADMIN_ID
    text = "Выберите кнопку ниже👇"
    markup = menu_main(admin)
    try:
        await _edit(call, text, markup)
    except Exception:
        await bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=markup)


async def handle_ask_stars(call):
    app.state.set(call.message.chat.id, {"type": "stars"})
    await bot.send_message(call.message.chat.id, "Введите количество ⭐️:", parse_mode="HTML")
    await bot.answer_callback_query(call.id)


EXACT_HANDLERS = {
    "admin_stats": handle_admin_stats,
    "send_yes": handle_send_yes,
    "send_no": handle_send_no,
    "schedule": handle_schedule,
    "mailing": handle_mailing,
    "bell": handle_bell,
    "sub": handle_sub,
    "unsub": handle_unsub,
    "main": handle_main,
    "ask_stars": handle_ask_stars,
}

PREFIX_HANDLERS = {
    "list_users": handle_list_users,
    "list_subs": handle_list_subs,
}


@bot.callback_query_handler(func=lambda c: c.data.startswith("day_"))
async def cb_day(call):
    day = call.data[len("day_"):]
    await track_user(app, call.message.chat.id, call.from_user)

    if day not in SCHEDULE_FILES:
        await bot.answer_callback_query(call.id, "неизвестный день")
        return

    info = SCHEDULE_FILES[day]
    await bot.answer_callback_query(call.id, "Загружаю...")
    await bot.send_chat_action(call.message.chat.id, "upload_photo")

    try:
        images = await app.schedule.get_or_fetch(day)
    except Exception:
        logger.exception("cb_day: не удалось получить расписание для %s", day)
        await bot.send_message(
            call.message.chat.id, f"❌Ошибка\n<a href=\"{info['link']}\">Открыть</a>",
            reply_markup=menu_days(), parse_mode="HTML",
        )
        return

    show_donate = app.should_show_donate(call.message.chat.id)
    caption = build_schedule_caption(info["name"], info["link"], show_donate)
    markup = menu_days(show_stars=show_donate)

    async def send(photo, **kwargs):
        await bot.send_photo(call.message.chat.id, photo, **kwargs)

    await send_photo_series(send, images, caption, markup, copy_bytes=True)


@bot.callback_query_handler(func=lambda c: True)
async def cb_dispatch(call):
    await track_user(app, call.message.chat.id, call.from_user)
    data = call.data

    handler = EXACT_HANDLERS.get(data)
    if handler is None and data in CALLS:
        handler = handle_calls_entry
    if handler is None:
        for prefix, prefix_handler in PREFIX_HANDLERS.items():
            if data.startswith(prefix):
                handler = prefix_handler
                break

    if handler is None:
        return

    try:
        await handler(call)
    except Exception:
        logger.exception("ошибка callback-хендлера для data=%s", data)
        await bot.answer_callback_query(call.id, "ошибка")
