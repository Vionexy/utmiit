from __future__ import annotations

import logging
from io import BytesIO

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InputMediaPhoto, Message

from config import MEDIA_GROUP_LIMIT

logger = logging.getLogger(__name__)


async def send_pages(
    bot: AsyncTeleBot,
    chat_id: int,
    pages: tuple[bytes, ...] | list[bytes],
    caption: str,
    markup: InlineKeyboardMarkup | None = None,
    file_ids: list[str] | None = None,
) -> list[str]:
    # у альбома нет inline-кнопок, кидаем их отдельным сообщением
    sources: list[str | BytesIO]
    if file_ids and len(file_ids) == len(pages):
        sources = list(file_ids)
    else:
        sources = [BytesIO(page) for page in pages]

    if len(sources) == 1:
        message = await bot.send_photo(
            chat_id, sources[0], caption=caption, parse_mode="HTML", reply_markup=markup
        )
        return _extract_file_ids([message])

    sent: list[Message] = []
    for offset in range(0, len(sources), MEDIA_GROUP_LIMIT):
        batch = sources[offset:offset + MEDIA_GROUP_LIMIT]
        media = [
            InputMediaPhoto(
                item,
                caption=caption if offset == 0 and index == 0 else None,
                parse_mode="HTML" if offset == 0 and index == 0 else None,
            )
            for index, item in enumerate(batch)
        ]
        sent.extend(await bot.send_media_group(chat_id, media))

    if markup is not None:
        await bot.send_message(chat_id, "Выберите день👇", reply_markup=markup)
    return _extract_file_ids(sent)


def _extract_file_ids(messages: list[Message]) -> list[str]:
    ids = []
    for message in messages:
        if message.photo:
            ids.append(message.photo[-1].file_id)
    return ids

