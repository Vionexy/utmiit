from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging

from telebot.types import BotCommand, BotCommandScopeChat

from app_context import app, bot
from check_loop import check_loop
from config import ADMIN_ID

# Импорт этих модулей регистрирует хендлеры в `bot` через декораторы.
import handlers_commands  # noqa: F401,E402
import handlers_callbacks  # noqa: F401,E402
import handlers_payments  # noqa: F401,E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def setup_commands() -> None:
    user_commands = [
        BotCommand("start", "🚀Старт"),
        BotCommand("schedule", "🗓️Расписание"),
        BotCommand("bell", "🔔Звонки"),
        BotCommand("mailing", "📣Рассылка"),
    ]
    await bot.set_my_commands(user_commands)

    admin_commands = user_commands + [
        BotCommand("stats", "📊Статистика"),
        BotCommand("publish", "📤Опубликовать расписание"),
        BotCommand("send", "📨Рассылка вручную"),
    ]
    await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID))


async def main() -> None:
    await app.db.init_schema()
    await setup_commands()
    asyncio.create_task(check_loop())
    logger.info("бот запущен")
    await bot.polling(non_stop=True, skip_pending=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("стоп")
    except Exception:
        logger.exception("критическая ошибка при запуске")
