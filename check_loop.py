from __future__ import annotations

import asyncio
import logging
import time

from app_context import app
from config import CHECK_ERROR_RETRY_SEC, CHECK_INTERVAL_SEC, SCHEDULE_FILES, today_local
from keyboards import broadcast_caption, menu_days
from schedule_service import ScheduleError, calc_hash, render_pages

logger = logging.getLogger(__name__)

MAINTENANCE_EVERY = 24 * 60 * 60


async def check_day(day: str, meta: dict) -> None:
    try:
        pdf_bytes = await app.schedule.download_pdf(meta["id"])
    except ScheduleError as exc:
        logger.warning("проверка %s пропущена: %s", day, exc)
        return

    current_hash = calc_hash(pdf_bytes)
    known_hash, last_sent = await app.db.get_hash(day)
    today = today_local()

    if current_hash == known_hash:
        if last_sent != today:
            await app.db.save_hash(day, current_hash, today)
        return

    pages = await asyncio.to_thread(render_pages, pdf_bytes)
    async with app.cache.lock(day):
        entry = app.cache.set(day, pages, current_hash)

    try:
        await app.publisher.publish_day(day, pages, current_hash, meta["link"])
    except Exception:
        logger.exception("публикация %s в github не удалась", day)

    subscribers = await app.db.get_subscriber_ids()
    if subscribers:
        caption = broadcast_caption(meta["name"], meta["link"])
        report, file_ids = await app.broadcaster.broadcast_pages(
            subscribers, entry.pages, caption, menu_days()
        )
        if file_ids:
            app.cache.remember_file_ids(day, file_ids)
        logger.info("рассылка %s: доставлено %s, ошибок %s", day, report.sent, report.failed)

    await app.db.save_hash(day, current_hash, today)


async def run_maintenance() -> None:
    removed = await app.db.purge_old_interactions()
    expired_states = app.state.purge_expired()
    idle_buckets = app.throttle.purge_idle()
    logger.info(
        "обслуживание: interactions -%s, состояний -%s, троттлинг -%s",
        removed,
        expired_states,
        idle_buckets,
    )


async def check_loop(stop_event: asyncio.Event | None = None) -> None:
    app.cache.clear()
    last_maintenance = 0.0
    while stop_event is None or not stop_event.is_set():
        try:
            app.last_check_time = time.time()
            for day, meta in SCHEDULE_FILES.items():
                try:
                    await check_day(day, meta)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("ошибка проверки дня %s", day)

            if time.time() - last_maintenance > MAINTENANCE_EVERY:
                last_maintenance = time.time()
                await run_maintenance()

            await _sleep(CHECK_INTERVAL_SEC, stop_event)
        except asyncio.CancelledError:
            logger.info("цикл проверки остановлен")
            raise
        except Exception:
            logger.exception("сбой цикла проверки")
            await _sleep(CHECK_ERROR_RETRY_SEC, stop_event)


async def _sleep(seconds: float, stop_event: asyncio.Event | None) -> None:
    if stop_event is None:
        await asyncio.sleep(seconds)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return
