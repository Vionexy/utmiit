from __future__ import annotations

import html
import logging
import time

from telebot.types import Message

from app_context import app, bot
from config import CHECK_INTERVAL_SEC, DAY_NAMES_SHORT, MAX_MESSAGE_LEN, SCHEDULE_FILES, today_local
from keyboards import (
    menu_calls,
    menu_days,
    menu_mail,
    menu_main,
    menu_send_confirm,
    menu_stats,
    stats_text,
)
from schedule_service import parse_day

logger = logging.getLogger(__name__)

PUBLISH_USAGE = (
    "Использование: <code>/publish пн|вт|ср|чт|пт|сб|все</code>\n"
    "Английские ключи (monday, tuesday, ...) тоже работают."
)


@bot.message_handler(commands=["start"])
async def cmd_start(msg: Message, is_admin: bool = False):
    name = html.escape(msg.from_user.first_name or "друг")
    await bot.send_message(
        msg.chat.id,
        f"Привет, {name}!\n\nЗдесь расписание колледжа и время звонков. Выбирай ниже 👇",
        reply_markup=menu_main(is_admin),
    )


@bot.message_handler(commands=["schedule"])
async def cmd_schedule(msg: Message):
    await bot.send_message(msg.chat.id, "Выберите день 👇", reply_markup=menu_days())


@bot.message_handler(commands=["bell"])
async def cmd_bell(msg: Message):
    await bot.send_message(msg.chat.id, "🔔 Расписание звонков", reply_markup=menu_calls())


@bot.message_handler(commands=["mailing"])
async def cmd_mailing(msg: Message):
    subscribed = await app.db.is_subscribed(msg.chat.id)
    text = (
        "✅ Вы подписаны — пришлём расписание, как только оно обновится."
        if subscribed
        else "🔕 Вы не подписаны на обновления расписания."
    )
    await bot.send_message(msg.chat.id, text, reply_markup=menu_mail(subscribed))


@bot.message_handler(commands=["cancel"])
async def cmd_cancel(msg: Message):
    state = app.state.pop(msg.chat.id)
    text = "Отменено." if state else "Нечего отменять."
    await bot.send_message(msg.chat.id, text)


@bot.message_handler(commands=["stats"], is_admin=True)
async def cmd_stats(msg: Message):
    stats = await app.db.get_stats()
    await bot.send_message(msg.chat.id, stats_text(stats), reply_markup=menu_stats())


@bot.message_handler(commands=["status"], is_admin=True)
async def cmd_status(msg: Message):
    lines = ["📋 <b>Состояние расписания</b>\n"]
    for day in SCHEDULE_FILES:
        last_hash, last_sent = await app.db.get_hash(day)
        name = DAY_NAMES_SHORT.get(day, day)
        if not last_hash:
            lines.append(f"▫️ <b>{name}</b>: данных нет")
            continue
        mark = "💾" if app.cache.is_fresh(day) else "▫️"
        lines.append(
            f"{mark} <b>{name}</b>: {last_sent or '—'}, hash <code>{last_hash[:8]}</code>"
        )

    stats = await app.db.get_stats()
    lines.append(
        f"\n👥 Всего: {stats.total} | Подписчиков: {stats.subscribers} | "
        f"Сегодня: {stats.daily} | Заблокировали: {stats.blocked}"
    )

    if app.last_check_time is None:
        lines.append("⏱ Проверка ещё не запускалась")
    else:
        left = max(0, CHECK_INTERVAL_SEC - int(time.time() - app.last_check_time))
        lines.append(f"⏱ Следующая проверка через ~{left // 60} мин {left % 60} сек")

    await bot.send_message(msg.chat.id, "\n".join(lines))


@bot.message_handler(commands=["publish"], is_admin=True)
async def cmd_publish(msg: Message):
    if not app.publisher.enabled:
        await bot.send_message(msg.chat.id, "Публикация выключена: нет GITHUB_TOKEN или GITHUB_REPO.")
        return

    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await bot.send_message(msg.chat.id, PUBLISH_USAGE)
        return

    target = parse_day(parts[1])
    if target == "all":
        days = list(SCHEDULE_FILES)
    elif target in SCHEDULE_FILES:
        days = [target]
    else:
        await bot.send_message(msg.chat.id, PUBLISH_USAGE)
        return

    await bot.send_message(msg.chat.id, f"⏳ Публикую: {', '.join(days)}")
    published_at = today_local()
    done, failed = [], []
    for day in days:
        try:
            pages = await app.schedule.publish(day, published_at)
            done.append(f"{day} ({pages} стр.)")
        except Exception as exc:
            logger.exception("publish: ошибка для %s", day)
            failed.append(f"{day}: {exc}")

    report = []
    if done:
        report.append("✅ Готово: " + ", ".join(done))
    if failed:
        report.append("❌ Ошибки: " + "; ".join(failed))
    await bot.send_message(msg.chat.id, "\n".join(report))


@bot.message_handler(commands=["send"], is_admin=True)
async def cmd_send(msg: Message):
    parts = msg.text.split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await bot.send_message(msg.chat.id, "Использование: <code>/send текст сообщения</code>")
        return
    if len(text) > MAX_MESSAGE_LEN:
        await bot.send_message(msg.chat.id, f"Слишком длинно: максимум {MAX_MESSAGE_LEN} символов.")
        return

    recipients = await app.db.get_active_user_ids()
    if not recipients:
        await bot.send_message(msg.chat.id, "Некому отправлять: активных пользователей нет.")
        return

    app.state.set(msg.chat.id, {"type": "send", "text": text, "recipients": recipients})
    await bot.send_message(
        msg.chat.id,
        f"Отправить <b>{len(recipients)}</b> пользователям?\n\n{text}",
        reply_markup=menu_send_confirm(),
    )

