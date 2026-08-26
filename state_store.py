from __future__ import annotations

import time
from typing import Any


class StateStore:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._data: dict[int, tuple[float, dict[str, Any]]] = {}

    def set(self, chat_id: int, value: dict[str, Any]) -> None:
        self._data[chat_id] = (time.monotonic(), value)

    def get(self, chat_id: int) -> dict[str, Any]:
        entry = self._data.get(chat_id)
        if entry is None:
            return {}
        created_at, value = entry
        if time.monotonic() - created_at > self._ttl:
            del self._data[chat_id]
            return {}
        return value

    def pop(self, chat_id: int) -> dict[str, Any]:
        entry = self._data.pop(chat_id, None)
        return entry[1] if entry else {}

    def purge_expired(self) -> int:
        deadline = time.monotonic() - self._ttl
        stale = [chat_id for chat_id, (created_at, _) in self._data.items() if created_at < deadline]
        for chat_id in stale:
            del self._data[chat_id]
        return len(stale)

    def __len__(self) -> int:
        return len(self._data)

