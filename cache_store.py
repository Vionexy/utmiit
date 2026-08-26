from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from config import CACHE_MAX_DAYS, CACHE_TTL


@dataclass(slots=True)
class CacheEntry:
    pages: tuple[bytes, ...]
    file_hash: str
    created_at: float
    file_ids: list[str] = field(default_factory=list)


class ScheduleCache:
    def __init__(self, ttl: int = CACHE_TTL, max_days: int = CACHE_MAX_DAYS) -> None:
        self._ttl = ttl
        self._max_days = max_days
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, day: str) -> asyncio.Lock:
        return self._locks.setdefault(day, asyncio.Lock())

    def get(self, day: str) -> CacheEntry | None:
        entry = self._data.get(day)
        if entry is None:
            return None
        if time.monotonic() - entry.created_at >= self._ttl:
            del self._data[day]
            return None
        self._data.move_to_end(day)
        return entry

    def set(self, day: str, pages: list[bytes], file_hash: str) -> CacheEntry:
        entry = CacheEntry(pages=tuple(pages), file_hash=file_hash, created_at=time.monotonic())
        self._data[day] = entry
        self._data.move_to_end(day)
        while len(self._data) > self._max_days:
            self._data.popitem(last=False)
        return entry

    def remember_file_ids(self, day: str, file_ids: list[str]) -> None:
        entry = self._data.get(day)
        if entry is not None:
            entry.file_ids = file_ids

    def is_fresh(self, day: str) -> bool:
        return self.get(day) is not None

    def clear(self) -> None:
        self._data.clear()

