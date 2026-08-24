from __future__ import annotations

from io import BytesIO
from typing import Awaitable, Callable

SendPhoto = Callable[..., Awaitable[None]]


async def send_photo_series(send: SendPhoto, images: list[BytesIO], caption: str, markup, copy_bytes: bool = False) -> None:
    for index, img in enumerate(images):
        img.seek(0)
        photo = BytesIO(img.read()) if copy_bytes else img
        if copy_bytes:
            img.seek(0)
        is_last = index == len(images) - 1
        await send(
            photo,
            caption=caption if is_last else None,
            parse_mode="HTML" if is_last else None,
            reply_markup=markup if is_last else None,
        )
