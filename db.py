from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass

import aiosqlite

from config import DB_PATH, INTERACTIONS_KEEP_DAYS, today_local

logger = logging.getLogger(__name__)

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS subscribers (
           chat_id INTEGER PRIMARY KEY,
           joined_date TEXT NOT NULL
       )""",
    """CREATE TABLE IF NOT EXISTS schedule_updates (
           day TEXT PRIMARY KEY,
           last_hash TEXT,
           last_sent_date TEXT
       )""",
    """CREATE TABLE IF NOT EXISTS all_users (
           chat_id INTEGER PRIMARY KEY,
           first_name TEXT,
           last_name TEXT,
           username TEXT,
           first_interaction_date TEXT NOT NULL
       )""",
    # PRIMARY KEY по паре, чтобы не плодить строки за один день
    """CREATE TABLE IF NOT EXISTS interactions (
           chat_id INTEGER NOT NULL,
           interaction_date TEXT NOT NULL,
           PRIMARY KEY (chat_id, interaction_date)
       ) WITHOUT ROWID""",
    "CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(interaction_date)",
    "CREATE INDEX IF NOT EXISTS idx_users_first_seen ON all_users(first_interaction_date DESC)",
)


@dataclass(frozen=True, slots=True)
class UserRecord:
    chat_id: int
    first_name: str
    last_name: str
    username: str

    def display(self) -> str:
        full_name = " ".join(part for part in (self.first_name, self.last_name) if part)
        title = html.escape(full_name) or "без имени"
        if self.username:
            handle = html.escape(self.username)
            return f'<a href="https://t.me/{handle}">@{handle}</a> — {title}'
        return f"{title} (<code>{self.chat_id}</code>)"


@dataclass(frozen=True, slots=True)
class Stats:
    total: int
    subscribers: int
    daily: int


class Database:
    def __init__(self, path: str = DB_PATH) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is None:
                conn = await aiosqlite.connect(self._path)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA busy_timeout=5000")
                self._conn = conn
        return self._conn

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def init_schema(self) -> None:
        db = await self.connect()
        for statement in SCHEMA:
            await db.execute(statement)
        await self._fix_interactions(db)
        await db.commit()

    async def _fix_interactions(self, db: aiosqlite.Connection) -> None:
        """Старая таблица создавалась без ключа, поэтому одно и то же
        посещение писалось столько раз, сколько человек нажимал кнопки."""
        cur = await db.execute("PRAGMA index_list(interactions)")
        if any(row["origin"] == "pk" for row in await cur.fetchall()):
            return

        await db.execute("ALTER TABLE interactions RENAME TO interactions_old")
        await db.execute(
            """CREATE TABLE interactions (
                   chat_id INTEGER NOT NULL,
                   interaction_date TEXT NOT NULL,
                   PRIMARY KEY (chat_id, interaction_date)
               ) WITHOUT ROWID"""
        )
        await db.execute(
            """INSERT INTO interactions (chat_id, interaction_date)
               SELECT DISTINCT chat_id, interaction_date FROM interactions_old"""
        )
        cur = await db.execute("SELECT COUNT(*) FROM interactions_old")
        before = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM interactions")
        after = (await cur.fetchone())[0]
        await db.execute("DROP TABLE interactions_old")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(interaction_date)"
        )
        logger.info("посещения пересобраны: было %s строк, осталось %s", before, after)

    # --- пользователи ---------------------------------------------------

    async def track_users(self, records: list[UserRecord]) -> None:
        if not records:
            return
        db = await self.connect()
        today = today_local()
        await db.executemany(
            """INSERT INTO all_users (chat_id, first_name, last_name, username, first_interaction_date)
               VALUES (?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   first_name = excluded.first_name,
                   last_name = excluded.last_name,
                   username = excluded.username""",
            [(r.chat_id, r.first_name, r.last_name, r.username, today) for r in records],
        )
        await db.executemany(
            "INSERT OR IGNORE INTO interactions (chat_id, interaction_date) VALUES (?,?)",
            [(r.chat_id, today) for r in records],
        )
        await db.commit()

    async def is_subscribed(self, chat_id: int) -> bool:
        db = await self.connect()
        cur = await db.execute("SELECT 1 FROM subscribers WHERE chat_id=?", (chat_id,))
        return await cur.fetchone() is not None

    async def add_sub(self, chat_id: int) -> None:
        db = await self.connect()
        await db.execute(
            "INSERT OR IGNORE INTO subscribers (chat_id, joined_date) VALUES (?,?)",
            (chat_id, today_local()),
        )
        await db.commit()

    async def del_sub(self, chat_id: int) -> None:
        db = await self.connect()
        await db.execute("DELETE FROM subscribers WHERE chat_id=?", (chat_id,))
        await db.commit()

    async def get_subscriber_ids(self) -> list[int]:
        return await self._fetch_ids("SELECT chat_id FROM subscribers")

    async def get_all_user_ids(self) -> list[int]:
        return await self._fetch_ids("SELECT chat_id FROM all_users")

    async def _fetch_ids(self, query: str) -> list[int]:
        db = await self.connect()
        cur = await db.execute(query)
        return [row[0] for row in await cur.fetchall()]

    # --- расписание -----------------------------------------------------

    async def get_hash(self, day: str) -> tuple[str | None, str | None]:
        db = await self.connect()
        cur = await db.execute(
            "SELECT last_hash, last_sent_date FROM schedule_updates WHERE day=?", (day,)
        )
        row = await cur.fetchone()
        return (row["last_hash"], row["last_sent_date"]) if row else (None, None)

    async def save_hash(self, day: str, file_hash: str, date: str) -> None:
        db = await self.connect()
        await db.execute(
            """INSERT INTO schedule_updates (day, last_hash, last_sent_date) VALUES (?,?,?)
               ON CONFLICT(day) DO UPDATE SET last_hash=excluded.last_hash,
                                             last_sent_date=excluded.last_sent_date""",
            (day, file_hash, date),
        )
        await db.commit()

    # --- статистика -----------------------------------------------------

    async def get_stats(self) -> Stats:
        db = await self.connect()
        cur = await db.execute(
            """SELECT
                   (SELECT COUNT(*) FROM all_users) AS total,
                   (SELECT COUNT(*) FROM subscribers) AS subs,
                   (SELECT COUNT(DISTINCT chat_id) FROM interactions WHERE interaction_date=?) AS daily""",
            (today_local(),),
        )
        row = await cur.fetchone()
        return Stats(total=row["total"], subscribers=row["subs"], daily=row["daily"])

    async def count_users(self) -> int:
        return await self._count("SELECT COUNT(*) FROM all_users")

    async def count_subscribers(self) -> int:
        return await self._count("SELECT COUNT(*) FROM subscribers")

    async def _count(self, query: str) -> int:
        db = await self.connect()
        cur = await db.execute(query)
        return (await cur.fetchone())[0]

    async def page_users(self, limit: int, offset: int) -> list[UserRecord]:
        return await self._page(
            """SELECT chat_id, first_name, last_name, username FROM all_users
               ORDER BY first_interaction_date DESC, chat_id DESC
               LIMIT ? OFFSET ?""",
            limit,
            offset,
        )

    async def page_subscribers(self, limit: int, offset: int) -> list[UserRecord]:
        return await self._page(
            """SELECT s.chat_id, u.first_name, u.last_name, u.username
               FROM subscribers s
               LEFT JOIN all_users u ON u.chat_id = s.chat_id
               ORDER BY s.joined_date DESC, s.chat_id DESC
               LIMIT ? OFFSET ?""",
            limit,
            offset,
        )

    async def _page(self, query: str, limit: int, offset: int) -> list[UserRecord]:
        db = await self.connect()
        cur = await db.execute(query, (limit, offset))
        return [
            UserRecord(
                chat_id=row["chat_id"],
                first_name=row["first_name"] or "",
                last_name=row["last_name"] or "",
                username=row["username"] or "",
            )
            for row in await cur.fetchall()
        ]

    async def purge_old_interactions(self, keep_days: int = INTERACTIONS_KEEP_DAYS) -> int:
        db = await self.connect()
        cur = await db.execute(
            "DELETE FROM interactions WHERE interaction_date < date(?, ?)",
            (today_local(), f"-{keep_days} days"),
        )
        await db.commit()
        return cur.rowcount or 0

