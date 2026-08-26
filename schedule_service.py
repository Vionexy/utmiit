from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx
import pymupdf

from cache_store import CacheEntry, ScheduleCache
from config import DAY_MAP, RENDER_DPI, SCHEDULE_FILES
from db import Database
from github_publish import GithubPublisher

logger = logging.getLogger(__name__)

DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf"}


class ScheduleError(RuntimeError):
    pass


def calc_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_day(raw: str | None) -> str | None:
    if not raw:
        return None
    normalized = raw.strip().lower()
    return DAY_MAP.get(normalized, normalized)


def render_pages(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> list[bytes]:
    # cpu-bound, гонять через asyncio.to_thread
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise ScheduleError("в PDF нет страниц")
        return [doc.load_page(i).get_pixmap(dpi=dpi).tobytes("png") for i in range(doc.page_count)]


class ScheduleService:
    def __init__(self, db: Database, cache: ScheduleCache, publisher: GithubPublisher) -> None:
        self._db = db
        self._cache = cache
        self._publisher = publisher
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers=DOWNLOAD_HEADERS,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def download_pdf(self, file_id: str) -> bytes:
        client = await self._http()
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        last_error = "неизвестная ошибка"
        for attempt in range(DOWNLOAD_ATTEMPTS):
            try:
                resp = await client.get(url)
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}"
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                if not resp.content.startswith(b"%PDF"):
                    # drive отдаёт html-заглушку, если файл закрыт
                    raise ScheduleError("Google Drive вернул не PDF (проверь доступ к файлу)")
                return resp.content
            except ScheduleError:
                raise
            except httpx.HTTPError as exc:
                last_error = str(exc)
                logger.warning("download_pdf %s: попытка %s не удалась: %s", file_id, attempt + 1, exc)
                if attempt < DOWNLOAD_ATTEMPTS - 1:
                    await asyncio.sleep(2 ** attempt)
        raise ScheduleError(f"не удалось скачать PDF: {last_error}")

    async def fetch_pages(self, day: str) -> tuple[list[bytes], str]:
        pdf_bytes = await self.download_pdf(SCHEDULE_FILES[day]["id"])
        pages = await asyncio.to_thread(render_pages, pdf_bytes)
        return pages, calc_hash(pdf_bytes)

    async def get_or_fetch(self, day: str) -> CacheEntry:
        async with self._cache.lock(day):
            cached = self._cache.get(day)
            if cached is not None:
                return cached
            pages, file_hash = await self.fetch_pages(day)
            return self._cache.set(day, pages, file_hash)

    async def publish(self, day: str, published_at: str) -> int:
        async with self._cache.lock(day):
            pages, file_hash = await self.fetch_pages(day)
            self._cache.set(day, pages, file_hash)
        await self._publisher.publish_day(day, pages, file_hash, SCHEDULE_FILES[day]["link"])
        await self._db.save_hash(day, file_hash, published_at)
        return len(pages)

