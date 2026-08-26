from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal

from telebot.asyncio_helper import ApiTelegramException
from telebot.async_telebot import ExceptionHandler
from telebot.types import BotCommand, BotCommandScopeChat

import config
from app_context import app, bot
from check_loop import check_loop
from middleware import IsAdmin

# хендлеры регистрируются при импорте
import handlers_commands  # noqa: E402,F401
import handlers_payments  # noqa: E402,F401
import handlers_callbacks  # noqa: E402,F401

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand("start", "🚀 Старт"),
    BotCommand("schedule", "🗓️ Расписание"),
    BotCommand("bell", "🔔 Звонки"),
    BotCommand("mailing", "📣 Подписка на обновления"),
    BotCommand("cancel", "✖️ Отменить ввод"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("stats", "📊 Статистика"),
    BotCommand("status", "📋 Состояние расписания"),
    BotCommand("publish", "📤 Опубликовать расписание"),
    BotCommand("send", "📨 Рассылка вручную"),
]

ALLOWED_UPDATES = ["message", "callback_query", "pre_checkout_query"]


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if config.LOG_FILE:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                config.LOG_FILE,
                maxBytes=config.LOG_MAX_BYTES,
                backupCount=config.LOG_BACKUPS,
                encoding="utf-8",
            )
        )
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class PollingExceptionHandler(ExceptionHandler):
    def handle(self, exception: Exception) -> bool:
        if isinstance(exception, ApiTelegramException):
            logger.error("ошибка Telegram API %s: %s", exception.error_code, exception.description)
            return True
        logger.exception("ошибка polling", exc_info=exception)
        return True


async def setup_commands() -> None:
    await bot.set_my_commands(USER_COMMANDS)
    await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=config.ADMIN_ID))


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # на windows не работает, там ловим KeyboardInterrupt
            pass


async def main() -> None:
    config.validate()
    bot.exception_handler = PollingExceptionHandler()
    bot.add_custom_filter(IsAdmin())
    app.setup_middlewares()

    await app.db.init_schema()
    await setup_commands()

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)
    app.tracker.start()
    checker = asyncio.create_task(check_loop(stop_event), name="schedule-checker")

    me = await bot.get_me()
    logger.info("бот @%s запущен", me.username)

    polling = asyncio.create_task(
        bot.polling(non_stop=True, allowed_updates=ALLOWED_UPDATES, request_timeout=60),
        name="polling",
    )
    stopper = asyncio.create_task(stop_event.wait(), name="stop-waiter")

    try:
        await asyncio.wait({polling, stopper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop_event.set()
        for task in (polling, stopper, checker):
            task.cancel()
        await asyncio.gather(polling, stopper, checker, return_exceptions=True)
        await bot.close_session()
        await app.shutdown()
        logger.info("бот остановлен")


def run() -> None:
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("остановка по Ctrl+C")
    except config.ConfigError as exc:
        logger.error("ошибка конфигурации: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    run()

