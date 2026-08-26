from __future__ import annotations

import logging
from collections import OrderedDict

from telebot.async_telebot import AsyncTeleBot

from broadcast import Broadcaster
from cache_store import ScheduleCache
from config import API_TOKEN, DONATE_EVERY, VIEW_COUNTER_MAX
from db import Database
from github_publish import GithubPublisher
from middleware import ThrottleMiddleware, TrackingMiddleware, UserTracker
from schedule_service import ScheduleService
from state_store import StateStore

logger = logging.getLogger(__name__)


class AppContext:
    def __init__(self) -> None:
        self.bot = AsyncTeleBot(API_TOKEN, parse_mode="HTML")
        self.db = Database()
        self.cache = ScheduleCache()
        self.publisher = GithubPublisher()
        self.schedule = ScheduleService(self.db, self.cache, self.publisher)
        self.broadcaster = Broadcaster(self.bot, self.db)
        self.state = StateStore()
        self.tracker = UserTracker(self.db)
        self.throttle = ThrottleMiddleware()
        self.last_check_time: float | None = None
        self._views: OrderedDict[int, int] = OrderedDict()

    def setup_middlewares(self) -> None:
        self.bot.setup_middleware(self.throttle)
        self.bot.setup_middleware(TrackingMiddleware(self.tracker))

    def should_show_donate(self, user_id: int) -> bool:
        count = self._views.get(user_id, 0) + 1
        self._views[user_id] = count
        self._views.move_to_end(user_id)
        while len(self._views) > VIEW_COUNTER_MAX:
            self._views.popitem(last=False)
        return count % DONATE_EVERY == 0

    async def shutdown(self) -> None:
        await self.tracker.stop()
        await self.schedule.aclose()
        await self.publisher.aclose()
        await self.db.close()
        self.cache.clear()
        logger.info("ресурсы освобождены")


app = AppContext()
bot = app.bot

