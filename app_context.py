from __future__ import annotations

from collections import defaultdict

from telebot.async_telebot import AsyncTeleBot

from broadcast import Broadcaster
from cache_store import ScheduleCache
from config import API_TOKEN, DONATE_EVERY
from db import Database
from schedule_service import ScheduleService
from state_store import StateStore


class AppContext:
    def __init__(self) -> None:
        self.bot = AsyncTeleBot(API_TOKEN)
        self.db = Database()
        self.cache = ScheduleCache()
        self.schedule = ScheduleService(self.db, self.cache)
        self.broadcaster = Broadcaster(self.bot, self.db)
        self.state = StateStore()
        self.view_count: dict[int, int] = defaultdict(int)
        self.last_check_time: float | None = None

    def should_show_donate(self, user_id: int) -> bool:
        self.view_count[user_id] += 1
        return self.view_count[user_id] % DONATE_EVERY == 0


app = AppContext()
bot = app.bot
