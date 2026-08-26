from __future__ import annotations

import asyncio
import logging
import time

from telebot.asyncio_filters import AdvancedCustomFilter, SimpleCustomFilter
from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate
from telebot.types import CallbackQuery, Message, User

from config import (
    ADMIN_ID,
    THROTTLE_BURST,
    THROTTLE_RATE_SEC,
    TRACK_FLUSH_INTERVAL_SEC,
    TRACK_QUEUE_MAX,
)
from db import Database, UserRecord

logger = logging.getLogger(__name__)


class IsAdmin(SimpleCustomFilter):
    key = "is_admin"

    async def check(self, message: Message | CallbackQuery) -> bool:
        user = message.from_user
        return user is not None and user.id == ADMIN_ID


class CallbackDataFilter(AdvancedCustomFilter):
    # без него хендлеры с config=CallbackData(...).filter() не срабатывают
    key = "config"

    async def check(self, call: CallbackQuery, config) -> bool:
        return config.check(call)


class UserTracker:
    def __init__(self, db: Database, flush_interval: float = TRACK_FLUSH_INTERVAL_SEC) -> None:
        self._db = db
        self._interval = flush_interval
        self._pending: dict[int, UserRecord] = {}
        self._task: asyncio.Task | None = None

    def add(self, chat_id: int, user: User) -> None:
        if len(self._pending) >= TRACK_QUEUE_MAX:
            logger.warning("очередь трекинга переполнена, запись пропущена")
            return
        self._pending[chat_id] = UserRecord(
            chat_id=chat_id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username or "",
        )

    async def flush(self) -> int:
        if not self._pending:
            return 0
        batch = list(self._pending.values())
        self._pending.clear()
        try:
            await self._db.track_users(batch)
        except Exception:
            logger.exception("не удалось записать %s пользователей", len(batch))
            return 0
        return len(batch)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="user-tracker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.flush()


class TrackingMiddleware(BaseMiddleware):
    update_sensitive = False
    update_types = ["message", "callback_query"]

    def __init__(self, tracker: UserTracker) -> None:
        super().__init__()
        self._tracker = tracker

    async def pre_process(self, message: Message | CallbackQuery, data: dict) -> None:
        user = message.from_user
        chat = message.chat if isinstance(message, Message) else message.message.chat
        if user is None or user.is_bot:
            return
        data["is_admin"] = user.id == ADMIN_ID
        self._tracker.add(chat.id, user)

    async def post_process(self, message, data: dict, exception) -> None:
        if exception is not None:
            logger.error("хендлер упал: %s", exception, exc_info=exception)


class ThrottleMiddleware(BaseMiddleware):
    update_sensitive = True
    update_types = ["message", "callback_query"]

    def __init__(self, rate: float = THROTTLE_RATE_SEC, burst: int = THROTTLE_BURST) -> None:
        super().__init__()
        self._rate = rate
        self._burst = burst
        self._buckets: dict[int, tuple[float, float]] = {}

    def _allow(self, user_id: int) -> bool:
        if user_id == ADMIN_ID:
            return True
        now = time.monotonic()
        tokens, last_seen = self._buckets.get(user_id, (float(self._burst), now))
        tokens = min(self._burst, tokens + (now - last_seen) / self._rate)
        if tokens < 1:
            self._buckets[user_id] = (tokens, now)
            return False
        self._buckets[user_id] = (tokens - 1, now)
        return True

    def purge_idle(self, idle_seconds: float = 3600) -> int:
        deadline = time.monotonic() - idle_seconds
        stale = [uid for uid, (_, last_seen) in self._buckets.items() if last_seen < deadline]
        for uid in stale:
            del self._buckets[uid]
        return len(stale)

    async def pre_process_message(self, message: Message, data: dict):
        if self._allow(message.from_user.id):
            return None
        logger.debug("троттлинг сообщения от %s", message.from_user.id)
        return CancelUpdate()

    async def pre_process_callback_query(self, call: CallbackQuery, data: dict):
        if self._allow(call.from_user.id):
            return None
        return CancelUpdate()

    async def post_process_message(self, message, data, exception) -> None:
        return None

    async def post_process_callback_query(self, call, data, exception) -> None:
        return None

