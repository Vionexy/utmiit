from __future__ import annotations

import pytest

from db import Database, UserRecord


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init_schema()
    yield database
    await database.close()


def user(chat_id: int, username: str = "") -> UserRecord:
    return UserRecord(chat_id=chat_id, first_name="Иван", last_name="Петров", username=username)


async def test_track_dedupes(db):
    await db.track_users([user(1), user(2)])
    await db.track_users([user(1), user(1)])

    stats = await db.get_stats()
    assert stats.total == 2
    assert stats.daily == 2


async def test_track_updates_profile(db):
    await db.track_users([user(1, "old_name")])
    await db.track_users([user(1, "new_name")])

    page = await db.page_users(10, 0)
    assert [u.username for u in page] == ["new_name"]


async def test_sub_unsub(db):
    await db.track_users([user(5)])
    assert await db.is_subscribed(5) is False

    await db.add_sub(5)
    assert await db.is_subscribed(5) is True
    assert await db.get_subscriber_ids() == [5]

    await db.del_sub(5)
    assert await db.is_subscribed(5) is False


async def test_blocked_not_in_targets(db):
    await db.track_users([user(1), user(2)])
    await db.add_sub(1)
    await db.add_sub(2)

    await db.mark_blocked(2)

    assert await db.get_subscriber_ids() == [1]
    assert await db.get_active_user_ids() == [1]
    stats = await db.get_stats()
    assert stats.blocked == 1
    assert stats.subscribers == 1


async def test_paging(db):
    await db.track_users([user(i) for i in range(1, 8)])

    first = await db.page_users(3, 0)
    second = await db.page_users(3, 3)

    assert len(first) == 3
    assert len(second) == 3
    assert {u.chat_id for u in first}.isdisjoint({u.chat_id for u in second})
    assert await db.count_users() == 7


async def test_purge_keeps_today(db):
    await db.track_users([user(1)])
    removed = await db.purge_old_interactions(keep_days=0)

    assert removed == 0
    stats = await db.get_stats()
    assert stats.daily == 1


async def test_hash_roundtrip(db):
    assert await db.get_hash("monday") == (None, None)

    await db.save_hash("monday", "abc", "2026-08-26")
    await db.save_hash("monday", "def", "2026-08-27")

    assert await db.get_hash("monday") == ("def", "2026-08-27")


def test_display_escapes_html():
    record = UserRecord(chat_id=7, first_name="<b>bad", last_name="", username="")
    assert "<b>" not in record.display()
    assert "&lt;b&gt;bad" in record.display()
