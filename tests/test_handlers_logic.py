from __future__ import annotations

import pytest
from telebot.asyncio_handler_backends import CancelUpdate

import config
from config import CALLS, DAY_TITLES, SCHEDULE_FILES
from keyboards import CALLS_CB, DAY_CB, PAGE_CB, menu_days, menu_pages
from middleware import ThrottleMiddleware, UserTracker
from schedule_service import parse_day


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeCall:
    def __init__(self, user_id: int) -> None:
        self.from_user = FakeUser(user_id)


class FakeData:
    def __init__(self, data: str) -> None:
        self.data = data


def labels(markup):
    return [button.text for row in markup.keyboard for button in row]


def test_day_cb_roundtrip():
    for key in SCHEDULE_FILES:
        data = DAY_CB.new(day=key)
        assert DAY_CB.parse(data)["day"] == key
        assert DAY_CB.filter(day=key).check(FakeData(data))


def test_page_cb_roundtrip():
    parsed = PAGE_CB.parse(PAGE_CB.new(kind="users", page=3))
    assert parsed["kind"] == "users"
    assert int(parsed["page"]) == 3


def test_calls_cb_covers_config():
    for kind in CALLS:
        assert CALLS_CB.parse(CALLS_CB.new(kind=kind))["kind"] == kind


def test_menu_days_marks_today():
    highlighted = [label for label in labels(menu_days()) if label.startswith("• ")]
    assert len(highlighted) == 1
    assert len(DAY_TITLES) == 6


def test_menu_pages_nav():
    first = labels(menu_pages("users", 1, 3))
    middle = labels(menu_pages("users", 2, 3))
    last = labels(menu_pages("users", 3, 3))

    assert "◀️" not in first
    assert "▶️" in first
    assert {"◀️", "▶️"}.issubset(set(middle))
    assert "▶️" not in last
    assert "1/3" in first


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("пн", "monday"), ("Суббота", "saturday"), ("все", "all"), ("MONDAY", "monday"), (None, None)],
)
def test_parse_day(raw, expected):
    assert parse_day(raw) == expected


def test_parse_day_unknown():
    assert parse_day("  Марс ") == "марс"


async def test_throttle_cancels_burst():
    middleware = ThrottleMiddleware(rate=10, burst=2)
    call = FakeCall(777)

    allowed = [await middleware.pre_process_callback_query(call, {}) for _ in range(4)]

    assert allowed[0] is None
    assert allowed[1] is None
    assert isinstance(allowed[2], CancelUpdate)
    assert isinstance(allowed[3], CancelUpdate)


async def test_throttle_skips_admin():
    middleware = ThrottleMiddleware(rate=100, burst=1)
    call = FakeCall(config.ADMIN_ID)

    results = [await middleware.pre_process_callback_query(call, {}) for _ in range(5)]
    assert all(result is None for result in results)


async def test_throttle_purge_idle():
    middleware = ThrottleMiddleware(rate=1, burst=1)
    await middleware.pre_process_callback_query(FakeCall(42), {})

    assert middleware.purge_idle(idle_seconds=0) == 1


class RecordingDb:
    def __init__(self) -> None:
        self.batches: list[list] = []

    async def track_users(self, records) -> None:
        self.batches.append(records)


async def test_tracker_batches():
    db = RecordingDb()
    tracker = UserTracker(db, flush_interval=0.01)

    class U:
        first_name = "Иван"
        last_name = "Петров"
        username = "ivan"
        is_bot = False

    tracker.add(1, U())
    tracker.add(1, U())
    tracker.add(2, U())

    written = await tracker.flush()

    assert written == 2
    assert len(db.batches) == 1
    assert await tracker.flush() == 0
