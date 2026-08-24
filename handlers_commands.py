from __future__ import annotations

import html
import logging
import time

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from app_context import app, bot
from config import ADMIN_ID, CHECK_INTERVAL_SEC, DAY_NAMES_SHORT, GITHUB_ENABLED, SCHEDULE_FILES, now_local
from keyboards import format_stats_text, menu_calls, menu_days, menu_main, menu_mail, menu_stats
from middleware import safe_handler, track_user
from schedule_service import parse_day

logger = logging.getLogger(__name__)


def _admin_only(msg) -> bool:
    return msg.chat.id == ADMIN_ID


@bot.message_handler(commands=["start"])
@safe_handler
async def cmd_start(msg):
    await track_user(app, msg.chat.id, msg.from_user)
    name = html.escape(msg.from_user.first_name or "")
    await bot.send_message(
        msg.chat.id, f"Привет, {name}!👇",
        parse_mode="HTML", reply_markup=menu_main(msg.chat.id == ADMIN_ID),
    )


@bot.message_handler(commands=["schedule"])
@safe_handler
async def cmd_schedule(msg):
    await track_user(app, msg.chat.id, msg.from_user)
    await bot.send_message(
        msg.chat.id, "Выберите день👇",
        parse_mode="HTML", reply_markup=menu_days(),
    )


@bot.message_handler(commands=["bell"])
@safe_handler
async def cmd_bell(msg):
    await track_user(app, msg.chat.id, msg.from_user)
    await bot.send_message(
        msg.chat.id, "Информация о звонках🔔",
        parse_mode="HTML", reply_markup=menu_calls(),
    )


@bot.message_handler(commands=["mailing"])
@safe_handler
async def cmd_mailing(msg):
    await track_user(app, msg.chat.id, msg.from_user)
    subscribed = await app.db.check_sub(msg.chat.id)
    text = "Вы подписаны✅" if subscribed else "Вы не подписаны"
    await bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=menu_mail(subscribed))


@bot.message_handler(commands=["stats"])
@safe_handler
async def cmd_stats(msg):
    if not _admin_only(msg):
        await bot.send_message(msg.chat.id, "нет доступа")
        return
    total, subs, daily = await app.db.get_stats()
    await bot.send_message(
        msg.chat.id, format_stats_text(total, subs, daily),
        parse_mode="HTML", reply_markup=menu_stats(),
    )


@bot.message_handler(commands=["status"])
@safe_handler
async def cmd_status(msg):
    if not _admin_only(msg):
        return
    lines = ["📋 <b>Статус расписания:</b>\n"]
    for day in SCHEDULE_FILES:
        last_hash, last_sent_date = await app.db.get_hash(day)
        in_cache = app.cache.is_fresh(day)
        name = DAY_NAMES_SHORT.get(day, day)
        if last_hash:
            short_hash = last_hash[:8]
            cached_mark = "💾" if in_cache else "  "
            lines.append(f"{cached_mark} <b>{name}</b>: обновлён {last_sent_date or '-'}, hash <code>{short_hash}</code>")
        else:
            lines.append(f"  <b>{name}</b>: нет данных")

    total, subs, daily = await app.db.get_stats()
    lines.append(f"\n👥 Всего: {total} | Подписаны: {subs} | Сегодня: {daily}")

    if app.last_check_time:
        elapsed = int(time.time() - app.last_check_time)
        next_check = max(0, CHECK_INTERVAL_SEC - elapsed)
        lines.append(f"⏱ Следующая проверка через ~{next_check // 60} мин {next_check % 60} сек")
    else:
        lines.append("⏱ Проверка ещё не запускалась")

    await bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="HTML")


@bot.message_handler(commands=["publish"])
@safe_handler
async def cmd_publish(msg):
    if not _admin_only(msg):
        await bot.send_message(msg.chat.id, "нет доступа")
        return
    if not GITHUB_ENABLED:
        await bot.send_message(msg.chat.id, "GITHUB_TOKEN/GITHUB_REPO не настроены.")
        return

    parts = msg.text.split(maxsplit=1)
    arg = parse_day(parts[1]) if len(parts) > 1 else None
    if arg == "all" or not arg:
        days = list(SCHEDULE_FILES.keys())
    elif arg in SCHEDULE_FILES:
        days = [arg]
    else:
        await bot.send_message(
            msg.chat.id,
            "Использование: /publish [monday|tuesday|...|saturday|all]\n"
            "Можно по-русски: пн, вт, ср, чт, пт, сб.",
        )
        return

    await bot.send_message(msg.chat.id, f"Публикую: {', '.join(days)}")
    now_str = now_local().strftime("%Y-%m-%d")
    ok, fail = [], []
    for day in days:
        try:
            pages = await app.schedule.push_day(day, now_str)
            ok.append(f"{day} ({pages} стр.)")
        except Exception as exc:
            logger.exception("publish: ошибка для %s", day)
            fail.append(f"{day}: {exc}")

    lines = []
    if ok:
        lines.append("Готово: " + ", ".join(ok))
    if fail:
        lines.append("Ошибки: " + "; ".join(fail))
    await bot.send_message(msg.chat.id, "\n".join(lines) if lines else "Нечего публиковать.")


@bot.message_handler(commands=["send"])
@safe_handler
async def cmd_send(msg):
    if not _admin_only(msg):
        return
    parts = msg.text.split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await bot.send_message(msg.chat.id, "Использование: /send твой текст")
        return
    users = await app.db.get_all_user_ids()
    app.state.set(msg.chat.id, {"type": "send", "text": text, "users": users})
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Отправить", callback_data="send_yes"),
        InlineKeyboardButton("Отмена", callback_data="send_no"),
    )
    await bot.send_message(
        msg.chat.id, f"Отправить <b>{len(users)}</b> пользователям?\n\n{text}",
        parse_mode="HTML", reply_markup=markup,
    )
