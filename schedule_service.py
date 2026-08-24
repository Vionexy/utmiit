from __future__ import annotations

import asyncio
import hashlib
import logging
from io import BytesIO

import fitz
import httpx
from PIL import Image

from cache_store import ScheduleCache
from config import DAY_MAP, SCHEDULE_FILES
from db import Database
from github_publish import publish_schedule_to_github

logger = logging.getLogger(__name__)


async def download_pdf(file_id: str) -> tuple[bytes | None, str | None]:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf"}
    last_error: str | None = None
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for attempt in range(3):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                if resp.content.startswith(b"%PDF"):
                    return resp.content, None
                return None, "ответ не является PDF"
            except Exception as exc:
                last_error = str(exc)
                logger.warning("download_pdf: попытка %s для %s не удалась: %s", attempt + 1, file_id, exc)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
    return None, last_error or "не удалось скачать после 3 попыток"


def make_images(pdf_bytes: bytes) -> list[BytesIO]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[BytesIO] = []
    try:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=False)
            buf.seek(0)
            images.append(buf)
    finally:
        doc.close()
    return images


def calc_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_day(raw: str | None) -> str | None:
    if not raw:
        return None
    return DAY_MAP.get(raw.strip().lower(), raw.strip().lower())


async def _fetch_and_render(day: str) -> tuple[list[BytesIO], str]:
    pdf_bytes, error = await download_pdf(SCHEDULE_FILES[day]["id"])
    if not pdf_bytes:
        raise RuntimeError(f"{day}: не удалось скачать PDF ({error})")
    images = await asyncio.to_thread(make_images, pdf_bytes)
    return images, calc_hash(pdf_bytes)


class ScheduleService:
    def __init__(self, db: Database, cache: ScheduleCache) -> None:
        self._db = db
        self._cache = cache

    async def load_day(self, day: str) -> tuple[list[BytesIO], str, str]:
        images, file_hash = await _fetch_and_render(day)
        return images, file_hash, SCHEDULE_FILES[day]["link"]

    async def push_day(self, day: str, now_str: str) -> int:
        images, file_hash, link = await self.load_day(day)
        self._cache.set(day, images, file_hash)
        await publish_schedule_to_github(day, images, file_hash, link)
        await self._db.save_hash(day, file_hash, now_str)
        return len(images)

    async def get_or_fetch(self, day: str) -> list[BytesIO]:
        async with self._cache.lock(day):
            cached = self._cache.get(day)
            if cached:
                return cached
            images, file_hash = await _fetch_and_render(day)
            self._cache.set(day, images, file_hash)
            return images
