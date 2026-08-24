from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from io import BytesIO

from config import CACHE_TTL


class ScheduleCache:
    def __init__(self, ttl: int = CACHE_TTL) -> None:
        self._ttl = ttl
        self._data: dict[str, dict] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock(self, day: str) -> asyncio.Lock:
        return self._locks[day]

    def get(self, day: str) -> list[BytesIO] | None:
        entry = self._data.get(day)
        if entry and time.time() - entry["time"] < self._ttl:
            return entry["imgs"]
        self._data.pop(day, None)
        return None

    def set(self, day: str, imgs: list[BytesIO], file_hash: str) -> None:
        self._data[day] = {"imgs": imgs, "hash": file_hash, "time": time.time()}

    def is_fresh(self, day: str) -> bool:
        entry = self._data.get(day)
        return bool(entry and time.time() - entry["time"] < self._ttl)

    def clear(self) -> None:
        self._data.clear()
