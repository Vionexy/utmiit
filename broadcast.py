from __future__ import annotations

import asyncio
import logging
import time
from io import BytesIO

from telebot.apihelper import ApiTelegramException

from config import SEND_CONCURRENCY, SEND_RATE_PER_SEC
from db import Database
from media import send_photo_series

logger = logging.getLogger(__name__)


class RateLimiter:
    # token bucket, чтобы не спамить телеграм быстрее лимита
    def __init__(self, rate: float) -> None:
        self._interval = 1.0 / rate
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval
            delay = start - now
        if delay > 0:
            await asyncio.sleep(delay)


class Broadcaster:
    def __init__(self, bot, db: Database, concurrency: int = SEND_CONCURRENCY, rate_per_sec: float = SEND_RATE_PER_SEC) -> None:
        self._bot = bot
        self._db = db
        self._semaphore = asyncio.Semaphore(concurrency)
        self._rate_limiter = RateLimiter(rate_per_sec)

    async def send_schedule_to_user(self, user_id: int, images: list[BytesIO], caption: str, markup) -> None:
        async def send(photo, **kwargs):
            await self._rate_limiter.acquire()
            await self._bot.send_photo(user_id, photo, **kwargs)

        async with self._semaphore:
            await send_photo_series(send, images, caption, markup)

    async def mass_send_schedule(self, user_ids: list[int], images: list[BytesIO], caption: str, markup) -> tuple[int, int]:
        img_bytes = []
        for img in images:
            img.seek(0)
            img_bytes.append(img.read())
            img.seek(0)

        def fresh_copies() -> list[BytesIO]:
            return [BytesIO(data) for data in img_bytes]

        async def send_one(user_id: int) -> bool:
            try:
                await self.send_schedule_to_user(user_id, fresh_copies(), caption, markup)
                return True
            except ApiTelegramException as exc:
                await self._handle_send_failure(user_id, exc)
                return False
            except Exception:
                logger.exception("рассылка расписания: ошибка для user_id=%s", user_id)
                return False

        results = await asyncio.gather(*[send_one(uid) for uid in user_ids])
        ok = sum(results)
        return ok, len(results) - ok

    async def mass_send_text(self, user_ids: list[int], text: str) -> tuple[int, int]:
        ok = err = 0
        for uid in user_ids:
            await self._rate_limiter.acquire()
            try:
                async with self._semaphore:
                    await self._bot.send_message(uid, text, parse_mode="HTML")
                ok += 1
            except ApiTelegramException as exc:
                await self._handle_send_failure(uid, exc)
                err += 1
            except Exception:
                logger.exception("рассылка текста: ошибка для user_id=%s", uid)
                err += 1
        return ok, err

    async def _handle_send_failure(self, user_id: int, exc: ApiTelegramException) -> None:
        message = str(exc).lower()
        if "blocked" in message or "chat not found" in message or "deactivated" in message:
            logger.info("user_id=%s недоступен (%s) - отписываю", user_id, exc)
            await self._db.del_sub(user_id)
        else:
            logger.warning("отправка не удалась для user_id=%s: %s", user_id, exc)
