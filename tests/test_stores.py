from __future__ import annotations

import time

from cache_store import ScheduleCache
from state_store import StateStore


def test_cache_evicts_oldest():
    cache = ScheduleCache(ttl=100, max_days=2)
    cache.set("monday", [b"a"], "h1")
    cache.set("tuesday", [b"b"], "h2")
    cache.set("wednesday", [b"c"], "h3")

    assert cache.get("monday") is None
    assert cache.get("tuesday") is not None
    assert cache.get("wednesday") is not None


def test_cache_read_bumps_order():
    cache = ScheduleCache(ttl=100, max_days=2)
    cache.set("monday", [b"a"], "h1")
    cache.set("tuesday", [b"b"], "h2")

    cache.get("monday")
    cache.set("wednesday", [b"c"], "h3")

    assert cache.get("monday") is not None
    assert cache.get("tuesday") is None


def test_cache_ttl():
    cache = ScheduleCache(ttl=0, max_days=2)
    cache.set("monday", [b"a"], "h1")
    assert cache.get("monday") is None
    assert cache.is_fresh("monday") is False


def test_cache_file_ids():
    cache = ScheduleCache(ttl=100, max_days=2)
    cache.set("monday", [b"a", b"b"], "h1")
    cache.remember_file_ids("monday", ["id1", "id2"])

    entry = cache.get("monday")
    assert entry.file_ids == ["id1", "id2"]
    assert entry.pages == (b"a", b"b")


def test_cache_lock_per_day():
    cache = ScheduleCache()
    assert cache.lock("monday") is cache.lock("monday")
    assert cache.lock("monday") is not cache.lock("tuesday")


def test_state_pop_once():
    store = StateStore(ttl_seconds=100)
    store.set(1, {"type": "send"})

    assert store.pop(1) == {"type": "send"}
    assert store.pop(1) == {}
    assert store.get(1) == {}


def test_state_purge():
    store = StateStore(ttl_seconds=0)
    store.set(1, {"type": "stars"})
    store.set(2, {"type": "send"})

    time.sleep(0.01)
    assert store.purge_expired() == 2
    assert len(store) == 0
