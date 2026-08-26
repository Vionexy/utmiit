from __future__ import annotations

import logging
import math

from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery

from app_context import app, bot
from config import CALLS, PAGE_SIZE, SCHEDULE_FILES
from keyboards import (
    ADMIN_STATS,
    ASK_STARS,
    BELL,
    CALLS_CB,
    DAY_CB,
    MAILING,
    MENU,
    NOOP,
    PAGE_CB,
    SCHEDULE,
    SEND_CANCEL,
    SEND_CONFIRM,
    SUB,
    UNSUB,
    menu_calls,
    menu_days,
    menu_mail,
    menu_main,
    menu_pages,
    menu_stats,
    schedule_caption,
    stats_text,
    users_page_text,
)
from media import send_pages
from schedule_service import ScheduleError

logger = logging.getLogger(__name__)

PAGE_SOURCES = {
    "users": ("Пользователи", "count_users", "page_users"),
    "subs": ("Подписчики", "count_subscribers", "page_subscribers"),
}

MAIL_ON = "✅ Вы подписаны — пришлём расписание, как только оно обновится."
MAIL_OFF = "🔕 Вы не подписаны на обновления расписания."


async def _edit(call: CallbackQuery, text: str, markup=None) -> None:
    try:
        await bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id, reply_markup=markup
        )
    except ApiTelegramException as exc:
        description = exc.description or ""
        if "message is not modified" in description:
            return
        if "no text in the message" in description or "message to edit not found" in description:
            await bot.send_message(call.message.chat.id, text, reply_markup=markup)
            return


@bot.callback_query_handler(func=lambda call: call.data == NOOP)
async def cb_noop(call: CallbackQuery):
    await bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == MENU)
async def cb_menu(call: CallbackQuery, is_admin: bool = False):
    await bot.answer_callback_query(call.id)
    await _edit(call, "Главное меню 👇", menu_main(is_admin))


@bot.callback_query_handler(func=lambda call: call.data == SCHEDULE)
async def cb_schedule(call: CallbackQuery):
    await bot.answer_callback_query(call.id)
    await _edit(call, "Выберите день 👇", menu_days())


@bot.callback_query_handler(func=lambda call: call.data == BELL)
async def cb_bell(call: CallbackQuery):
    await bot.answer_callback_query(call.id)
    await _edit(call, "🔔 Расписание звонков", menu_calls())


@bot.callback_query_handler(func=None, config=CALLS_CB.filter())
async def cb_calls(call: CallbackQuery):
    kind = CALLS_CB.parse(call.data)["kind"]
    text = CALLS.get(kind)
    if text is None:
        await bot.answer_callback_query(call.id, "Неизвестный раздел", show_alert=True)
        return
    await bot.answer_callback_query(call.id)
    await _edit(call, text, menu_calls(active=kind))


@bot.callback_query_handler(func=lambda call: call.data == MAILING)
async def cb_mailing(call: CallbackQuery):
    await bot.answer_callback_query(call.id)
    subscribed = await app.db.is_subscribed(call.message.chat.id)
    await _edit(call, MAIL_ON if subscribed else MAIL_OFF, menu_mail(subscribed))


@bot.callback_query_handler(func=lambda call: call.data in {SUB, UNSUB})
async def cb_subscription(call: CallbackQuery):
    chat_id = call.message.chat.id
    if call.data == SUB:
        await app.db.add_sub(chat_id)
        await bot.answer_callback_query(call.id, "Подписка включена")
        await _edit(call, MAIL_ON, menu_mail(True))
        return
    await app.db.del_sub(chat_id)
    await bot.answer_callback_query(call.id, "Подписка отключена")
    await _edit(call, MAIL_OFF, menu_mail(False))


@bot.callback_query_handler(func=None, config=DAY_CB.filter())
async def cb_day(call: CallbackQuery):
    day = DAY_CB.parse(call.data)["day"]
    if day not in SCHEDULE_FILES:
        await bot.answer_callback_query(call.id, "Неизвестный день", show_alert=True)
        return

    chat_id = call.message.chat.id
    meta = SCHEDULE_FILES[day]
    cached = app.cache.get(day)
    await bot.answer_callback_query(call.id, "" if cached else "Загружаю расписание…")
    if cached is None:
        await bot.send_chat_action(chat_id, "upload_photo")

    try:
        entry = cached or await app.schedule.get_or_fetch(day)
    except ScheduleError as exc:
        logger.warning("расписание %s недоступно: %s", day, exc)
        await bot.send_message(
            chat_id,
            f'Не удалось загрузить расписание.\n📎 <a href="{meta["link"]}">Открыть исходный файл</a>',
            reply_markup=menu_days(),
        )
        return

    show_donate = app.should_show_donate(call.from_user.id)
    caption = schedule_caption(meta["name"], meta["link"], show_donate)
    file_ids = await send_pages(
        bot, chat_id, entry.pages, caption, menu_days(show_stars=show_donate), entry.file_ids or None
    )
    if file_ids:
        app.cache.remember_file_ids(day, file_ids)


@bot.callback_query_handler(func=lambda call: call.data == ADMIN_STATS, is_admin=True)
async def cb_stats(call: CallbackQuery):
    await bot.answer_callback_query(call.id)
    stats = await app.db.get_stats()
    await _edit(call, stats_text(stats), menu_stats())


@bot.callback_query_handler(func=None, config=PAGE_CB.filter(), is_admin=True)
async def cb_page(call: CallbackQuery):
    parsed = PAGE_CB.parse(call.data)
    source = PAGE_SOURCES.get(parsed["kind"])
    if source is None:
        await bot.answer_callback_query(call.id, "Неизвестный список", show_alert=True)
        return

    title, count_method, page_method = source
    total = await getattr(app.db, count_method)()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(1, int(parsed["page"])), total_pages)
    users = await getattr(app.db, page_method)(PAGE_SIZE, (page - 1) * PAGE_SIZE)

    await bot.answer_callback_query(call.id)
    await _edit(
        call,
        users_page_text(title, users, page, total_pages, total),
        menu_pages(parsed["kind"], page, total_pages),
    )


@bot.callback_query_handler(func=lambda call: call.data == SEND_CONFIRM, is_admin=True)
async def cb_send_confirm(call: CallbackQuery):
    state = app.state.pop(call.message.chat.id)
    if state.get("type") != "send":
        await bot.answer_callback_query(call.id, "Черновик истёк, наберите /send заново", show_alert=True)
        return

    await bot.answer_callback_query(call.id)
    await _edit(call, "📣 Рассылка запущена…")
    report = await app.broadcaster.broadcast_text(state["recipients"], state["text"])
    await bot.send_message(
        call.message.chat.id,
        f"✅ Готово\nДоставлено: <b>{report.sent}</b>\nНе доставлено: <b>{report.failed}</b>",
    )


@bot.callback_query_handler(func=lambda call: call.data == SEND_CANCEL, is_admin=True)
async def cb_send_cancel(call: CallbackQuery):
    app.state.pop(call.message.chat.id)
    await bot.answer_callback_query(call.id, "Отменено")
    await _edit(call, "❌ Рассылка отменена.")


@bot.callback_query_handler(
    func=lambda call: call.data in {ADMIN_STATS, SEND_CONFIRM, SEND_CANCEL}
    or call.data.startswith("page:")
)
async def cb_admin_denied(call: CallbackQuery):
    await bot.answer_callback_query(call.id, "Раздел только для администратора", show_alert=True)


@bot.callback_query_handler(func=lambda call: True)
async def cb_unknown(call: CallbackQuery):
    logger.info("неизвестный callback_data=%s", call.data)
    await bot.answer_callback_query(call.id)
