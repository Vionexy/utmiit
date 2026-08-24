from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)


def safe_handler(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception:
            logger.exception("необработанная ошибка в хендлере %s", func.__name__)

    return wrapper


async def track_user(app, chat_id: int, user) -> None:
    await app.db.track_user(chat_id, user.first_name, user.last_name, user.username)
