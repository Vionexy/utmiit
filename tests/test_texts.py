from __future__ import annotations

from config import MAX_MESSAGE_LEN, PAGE_SIZE
from db import Stats, UserRecord
from keyboards import stats_text, users_page_text


def test_stats_text():
    text = stats_text(Stats(total=10, subscribers=4, daily=2, blocked=1))

    assert "10" in text
    assert "4" in text
    assert "2" in text
    assert "1" in text


def test_users_page_fits_limit():
    long = [
        UserRecord(chat_id=10**12 + i, first_name="Я" * 64, last_name="Ы" * 64, username="u" * 32)
        for i in range(PAGE_SIZE)
    ]
    text = users_page_text("Пользователи", long, 1, 4, 100)

    assert len(text) <= MAX_MESSAGE_LEN
    assert "обрезан" in text


def test_users_page_empty():
    assert "Пока никого" in users_page_text("Пользователи", [], 1, 1, 0)


def test_users_page_numbering_continues():
    users = [UserRecord(chat_id=i, first_name="И", last_name="", username="") for i in range(3)]
    text = users_page_text("Пользователи", users, 2, 3, 60)

    assert f"{PAGE_SIZE + 1}. " in text
