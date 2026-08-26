from __future__ import annotations

import asyncio

from telebot.apihelper import ApiTelegramException

from broadcast import Broadcaster, RateLimiter


class FakeDb:
    def __init__(self) -> None:
        self.blocked: list[int] = []

    async def mark_blocked(self, chat_id: int) -> None:
        self.blocked.append(chat_id)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_with: dict[int, Exception] = {}
        self.fail_once: dict[int, Exception] = {}

    async def send_message(self, chat_id: int, text: str, **kwargs):
        error = self.fail_once.pop(chat_id, None) or self.fail_with.get(chat_id)
        if error is not None:
            raise error
        self.sent.append((chat_id, text))


def api_error(code: int, description: str, params: dict | None = None) -> ApiTelegramException:
    payload = {"ok": False, "error_code": code, "description": description}
    if params:
        payload["parameters"] = params

    class Resp:
        text = str(payload)

    return ApiTelegramException("sendMessage", Resp(), payload)


def make_broadcaster(bot: FakeBot, db: FakeDb) -> Broadcaster:
    return Broadcaster(bot, db, concurrency=5, rate_per_sec=1000)


async def test_broadcast_text():
    bot, db = FakeBot(), FakeDb()
    report = await make_broadcaster(bot, db).broadcast_text([1, 2, 3], "привет")

    assert (report.sent, report.failed, report.total) == (3, 0, 3)
    assert len(bot.sent) == 3


async def test_blocked_marked():
    bot, db = FakeBot(), FakeDb()
    bot.fail_with[2] = api_error(403, "Forbidden: bot was blocked by the user")

    report = await make_broadcaster(bot, db).broadcast_text([1, 2], "привет")

    assert (report.sent, report.failed) == (1, 1)
    assert db.blocked == [2]


async def test_retry_after():
    bot, db = FakeBot(), FakeDb()
    bot.fail_once[1] = api_error(429, "Too Many Requests", {"retry_after": 0})

    report = await make_broadcaster(bot, db).broadcast_text([1], "привет")

    assert (report.sent, report.failed) == (1, 0)
    assert db.blocked == []


async def test_server_error_not_blocking():
    bot, db = FakeBot(), FakeDb()
    bot.fail_with[1] = api_error(500, "Internal Server Error")

    report = await make_broadcaster(bot, db).broadcast_text([1], "привет")

    assert (report.sent, report.failed) == (0, 1)
    assert db.blocked == []


async def test_one_crash_does_not_stop_rest():
    bot, db = FakeBot(), FakeDb()
    bot.fail_with[1] = RuntimeError("boom")

    report = await make_broadcaster(bot, db).broadcast_text([1, 2], "привет")

    assert (report.sent, report.failed) == (1, 1)


async def test_empty_list():
    bot, db = FakeBot(), FakeDb()
    report = await make_broadcaster(bot, db).broadcast_text([], "привет")

    assert (report.sent, report.failed) == (0, 0)


async def test_rate_limiter():
    limiter = RateLimiter(rate=50)
    started = asyncio.get_running_loop().time()
    for _ in range(5):
        await limiter.acquire()
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed >= 4 / 50
