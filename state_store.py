from __future__ import annotations

import time
from typing import Any


class StateStore:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._data: dict[int, dict[str, Any]] = {}
        self._timestamps: dict[int, float] = {}

    def set(self, chat_id: int, value: dict[str, Any]) -> None:
        self._data[chat_id] = value
        self._timestamps[chat_id] = time.time()

    def get(self, chat_id: int) -> dict[str, Any]:
        self._expire_if_needed(chat_id)
        return self._data.get(chat_id, {})

    def pop(self, chat_id: int) -> None:
        self._data.pop(chat_id, None)
        self._timestamps.pop(chat_id, None)

    def _expire_if_needed(self, chat_id: int) -> None:
        ts = self._timestamps.get(chat_id)
        if ts is not None and time.time() - ts > self._ttl:
            self.pop(chat_id)
