from __future__ import annotations

import pymupdf
import pytest
from telebot.types import InputMediaPhoto, Message, PhotoSize

from media import send_pages
from schedule_service import calc_hash, render_pages


def make_pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {index + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def test_render_returns_png():
    result = render_pages(make_pdf(3), dpi=40)

    assert len(result) == 3
    assert all(item.startswith(b"\x89PNG") for item in result)


def test_render_rejects_garbage():
    with pytest.raises(Exception):
        render_pages(b"not a pdf")


def test_calc_hash():
    assert calc_hash(b"abc") == calc_hash(b"abc")
    assert calc_hash(b"abc") != calc_hash(b"abd")


class FakeBot:
    def __init__(self) -> None:
        self.photo_calls: list[dict] = []
        self.group_calls: list[list[InputMediaPhoto]] = []
        self.messages: list[str] = []

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        self.photo_calls.append({"photo": photo, "caption": caption, "markup": reply_markup})
        return fake_message("single_id")

    async def send_media_group(self, chat_id, media):
        self.group_calls.append(media)
        return [fake_message(f"group_{i}") for i in range(len(media))]

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append(text)


def fake_message(file_id: str) -> Message:
    photo = PhotoSize.de_json({"file_id": file_id, "file_unique_id": file_id, "width": 1, "height": 1})
    return Message(
        message_id=1,
        from_user=None,
        date=0,
        chat=None,
        content_type="photo",
        options={"photo": [photo]},
        json_string={},
    )


async def test_one_page_via_send_photo():
    bot = FakeBot()
    file_ids = await send_pages(bot, 1, [b"a"], "подпись", markup="kb")

    assert len(bot.photo_calls) == 1
    assert bot.photo_calls[0]["caption"] == "подпись"
    assert bot.photo_calls[0]["markup"] == "kb"
    assert file_ids == ["single_id"]


async def test_many_pages_via_album():
    bot = FakeBot()
    file_ids = await send_pages(bot, 1, [b"a", b"b", b"c"], "подпись", markup="kb")

    assert len(bot.group_calls) == 1
    media = bot.group_calls[0]
    assert media[0].caption == "подпись"
    assert media[1].caption is None
    assert bot.messages
    assert file_ids == ["group_0", "group_1", "group_2"]


async def test_album_split_by_ten():
    bot = FakeBot()
    await send_pages(bot, 1, [b"x"] * 12, "подпись")

    assert [len(batch) for batch in bot.group_calls] == [10, 2]


async def test_file_ids_reused():
    bot = FakeBot()
    await send_pages(bot, 1, [b"a"], "подпись", file_ids=["cached_id"])

    assert bot.photo_calls[0]["photo"] == "cached_id"


async def test_file_ids_count_mismatch():
    bot = FakeBot()
    await send_pages(bot, 1, [b"a", b"b"], "подпись", file_ids=["only_one"])

    media = bot.group_calls[0]
    assert not isinstance(media[0].media, str)
