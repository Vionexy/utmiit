from __future__ import annotations

import asyncio
import logging
import time

from app_context import app
from config import CHECK_ERROR_RETRY_SEC, CHECK_INTERVAL_SEC, SCHEDULE_FILES
from github_publish import publish_schedule_to_github
from keyboards import build_broadcast_caption, menu_days
from schedule_service import calc_hash, download_pdf, make_images

logger = logging.getLogger(__name__)


async def _check_one_day(day: str, info: dict) -> None:
    pdf_bytes, error = await download_pdf(info["id"])
    if not pdf_bytes:
        logger.warning("не удалось скачать %s: %s", day, error)
        return

    cur_hash = calc_hash(pdf_bytes)
    old_hash, last_sent_date = await app.db.get_hash(day)
    today = time.strftime("%Y-%m-%d")

    if cur_hash == old_hash:
        if last_sent_date != today:
            await app.db.save_hash(day, cur_hash, today)
        logger.info("без изменений: %s", day)
        return

    async with app.cache.lock(day):
        images = await asyncio.to_thread(make_images, pdf_bytes)
        app.cache.set(day, images, cur_hash)

    try:
        await publish_schedule_to_github(day, images, cur_hash, info["link"])
    except Exception:
        logger.exception("github publish не удался для %s", day)

    subscribers = await app.db.get_subscriber_ids()
    if subscribers:
        caption = build_broadcast_caption(info["name"], info["link"])
        ok, fail = await app.broadcaster.mass_send_schedule(subscribers, images, caption, menu_days())
        logger.info("рассылка %s: %s ок, %s ошибок", day, ok, fail)

    await app.db.save_hash(day, cur_hash, today)


async def check_loop() -> None:
    app.cache.clear()
    while True:
        try:
            app.last_check_time = time.time()
            for day, info in SCHEDULE_FILES.items():
                try:
                    await _check_one_day(day, info)
                except Exception:
                    logger.exception("ошибка проверки дня %s", day)
            await asyncio.sleep(CHECK_INTERVAL_SEC)
        except Exception:
            logger.exception("ошибка цикла проверки")
            await asyncio.sleep(CHECK_ERROR_RETRY_SEC)
