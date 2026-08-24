from __future__ import annotations

import asyncio
import html
from datetime import datetime

import aiosqlite

from config import DB_PATH


class Database:
    def __init__(self, path: str = DB_PATH) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._init_lock:
            if self._conn is None:
                conn = await aiosqlite.connect(self._path)
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                self._conn = conn
        return self._conn

    async def init_schema(self) -> None:
        db = await self.connect()
        await db.execute(
            """CREATE TABLE IF NOT EXISTS subscribers
               (chat_id INTEGER PRIMARY KEY, joined_date TEXT)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS schedule_updates
               (day TEXT PRIMARY KEY, last_hash TEXT, last_sent_date TEXT)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS all_users
               (chat_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT,
                username TEXT, first_interaction_date TEXT)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS interactions
               (chat_id INTEGER, interaction_date TEXT)"""
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sub ON subscribers(chat_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_day ON schedule_updates(day)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_int ON interactions(interaction_date)")
        await db.commit()

    # --- пользователи -------------------------------------------------

    async def track_user(self, chat_id: int, fname: str | None, lname: str | None, uname: str | None) -> None:
        db = await self.connect()
        today = datetime.now().strftime("%Y-%m-%d")
        await db.execute(
            """INSERT INTO all_users (chat_id, first_name, last_name, username, first_interaction_date)
               VALUES (?,?,?,?,?)
               ON CONFLICT(chat_id) DO NOTHING""",
            (chat_id, fname or "", lname or "", uname or "", today),
        )
        await db.execute("INSERT INTO interactions VALUES (?,?)", (chat_id, today))
        await db.commit()

    async def check_sub(self, chat_id: int) -> bool:
        db = await self.connect()
        cur = await db.execute("SELECT 1 FROM subscribers WHERE chat_id=?", (chat_id,))
        return await cur.fetchone() is not None

    async def add_sub(self, chat_id: int) -> None:
        db = await self.connect()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("INSERT OR IGNORE INTO subscribers VALUES (?,?)", (chat_id, now))
        await db.commit()

    async def del_sub(self, chat_id: int) -> None:
        db = await self.connect()
        await db.execute("DELETE FROM subscribers WHERE chat_id=?", (chat_id,))
        await db.commit()

    async def get_subscriber_ids(self) -> list[int]:
        return await self._fetch_column("SELECT chat_id FROM subscribers")

    async def get_all_user_ids(self) -> list[int]:
        return await self._fetch_column("SELECT chat_id FROM all_users")

    async def _fetch_column(self, query: str) -> list[int]:
        db = await self.connect()
        cur = await db.execute(query)
        return [r[0] for r in await cur.fetchall()]

    # --- расписание -----------------------------------------------------

    async def get_hash(self, day: str) -> tuple[str | None, str | None]:
        db = await self.connect()
        cur = await db.execute(
            "SELECT last_hash, last_sent_date FROM schedule_updates WHERE day=?", (day,)
        )
        res = await cur.fetchone()
        return (res[0], res[1]) if res else (None, None)

    async def save_hash(self, day: str, file_hash: str, date: str) -> None:
        db = await self.connect()
        await db.execute("INSERT OR REPLACE INTO schedule_updates VALUES (?,?,?)", (day, file_hash, date))
        await db.commit()

    # --- статистика -----------------------------------------------------

    async def get_stats(self) -> tuple[int, int, int]:
        db = await self.connect()
        cur = await db.execute("SELECT COUNT(*) FROM all_users")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM subscribers")
        subs = (await cur.fetchone())[0]
        today = datetime.now().strftime("%Y-%m-%d")
        cur = await db.execute(
            "SELECT COUNT(DISTINCT chat_id) FROM interactions WHERE interaction_date=?", (today,)
        )
        daily = (await cur.fetchone())[0]
        return total, subs, daily

    async def get_users_list(self) -> list[str]:
        return await self._fetch_user_rows(
            """SELECT username, first_name, last_name FROM all_users
               WHERE username IS NOT NULL AND username != ''
               ORDER BY first_interaction_date DESC"""
        )

    async def get_subscribers_list(self) -> list[str]:
        return await self._fetch_user_rows(
            """SELECT u.username, u.first_name, u.last_name FROM all_users u
               INNER JOIN subscribers s ON u.chat_id = s.chat_id
               WHERE u.username IS NOT NULL AND u.username != ''
               ORDER BY s.joined_date DESC"""
        )

    async def _fetch_user_rows(self, query: str) -> list[str]:
        db = await self.connect()
        cur = await db.execute(query)
        return [self._format_user_row(r) for r in await cur.fetchall()]

    @staticmethod
    def _format_user_row(row) -> str:
        username, first_name, last_name = row
        return f"@{html.escape(username or '')} ({html.escape(first_name or '')} {html.escape(last_name or '')})"
