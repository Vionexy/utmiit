from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from telebot.apihelper import ApiTelegramException
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup

from config import SEND_CONCURRENCY, SEND_MAX_RETRIES, SEND_RATE_PER_SEC
from db import Database
from media import send_pages

logger = logging.getLogger(__name__)

# после 400/403 повторять смысла нет
PERMANENT_ERRORS = frozenset({400, 403})


@dataclass(frozen=True, slots=True)
class SendReport:
    sent: int
    failed: int

    @property
    def total(self) -> int:
        return self.sent + self.failed


class RateLimiter:
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
    def __init__(
        self,
        bot: AsyncTeleBot,
        db: Database,
        concurrency: int = SEND_CONCURRENCY,
        rate_per_sec: float = SEND_RATE_PER_SEC,
    ) -> None:
        self._bot = bot
        self._db = db
        self._semaphore = asyncio.Semaphore(concurrency)
        self._limiter = RateLimiter(rate_per_sec)

    async def _deliver(self, coro_factory) -> bool:
        for attempt in range(SEND_MAX_RETRIES):
            await self._limiter.acquire()
            try:
                async with self._semaphore:
                    await coro_factory()
                return True
            except ApiTelegramException as exc:
                retry_after = (exc.result_json.get("parameters") or {}).get("retry_after")
                if retry_after is not None and attempt < SEND_MAX_RETRIES - 1:
                    logger.warning("флуд-лимит telegram, пауза %s c", retry_after)
                    await asyncio.sleep(float(retry_after) + 0.5)
                    continue
                raise
        return False

    async def _send_to(self, chat_id: int, coro_factory) -> bool:
        try:
            return await self._deliver(coro_factory)
        except ApiTelegramException as exc:
            if exc.error_code in PERMANENT_ERRORS:
                logger.info("chat_id=%s недоступен (%s), помечаю заблокированным", chat_id, exc.description)
                await self._db.mark_blocked(chat_id)
            else:
                logger.warning("отправка в chat_id=%s не удалась: %s", chat_id, exc)
            return False
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("неожиданная ошибка отправки в chat_id=%s", chat_id)
            return False

    async def broadcast_text(self, chat_ids: list[int], text: str) -> SendReport:
        async def send(chat_id: int) -> bool:
            return await self._send_to(
                chat_id,
                lambda: self._bot.send_message(chat_id, text, parse_mode="HTML"),
            )

        return await self._run(chat_ids, send)

    async def broadcast_pages(
        self,
        chat_ids: list[int],
        pages: tuple[bytes, ...] | list[bytes],
        caption: str,
        markup: InlineKeyboardMarkup | None,
        file_ids: list[str] | None = None,
    ) -> tuple[SendReport, list[str]]:
        # первому грузим байты, дальше рассылаем file_id
        if not chat_ids:
            return SendReport(0, 0), list(file_ids or [])

        known_ids = list(file_ids or [])
        head, *rest = chat_ids
        sent = failed = 0

        if known_ids:
            head_ok = await self._send_to(
                head, lambda: send_pages(self._bot, head, pages, caption, markup, known_ids)
            )
        else:
            head_ok, uploaded = await self._upload_first(head, pages, caption, markup)
            known_ids = uploaded
        sent, failed = (1, 0) if head_ok else (0, 1)

        async def send(chat_id: int) -> bool:
            return await self._send_to(
                chat_id,
                lambda: send_pages(self._bot, chat_id, pages, caption, markup, known_ids or None),
            )

        report = await self._run(rest, send)
        return SendReport(report.sent + sent, report.failed + failed), known_ids

    async def _upload_first(
        self,
        chat_id: int,
        pages: tuple[bytes, ...] | list[bytes],
        caption: str,
        markup: InlineKeyboardMarkup | None,
    ) -> tuple[bool, list[str]]:
        uploaded: list[str] = []

        async def upload() -> None:
            nonlocal uploaded
            uploaded = await send_pages(self._bot, chat_id, pages, caption, markup)

        ok = await self._send_to(chat_id, upload)
        return ok, uploaded

    async def _run(self, chat_ids: list[int], send) -> SendReport:
        if not chat_ids:
            return SendReport(0, 0)
        results = await asyncio.gather(*(send(chat_id) for chat_id in chat_ids))
        sent = sum(1 for ok in results if ok)
        return SendReport(sent=sent, failed=len(results) - sent)

