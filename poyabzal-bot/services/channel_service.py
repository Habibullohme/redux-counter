"""Kanalga joylash va kanaldan o'chirish.

`remove_product_posts` — keyinchalik web sayt bilan integratsiyada ishlatiladi:
sayt "yuk tugadi" deganda aynan shu funksiya chaqiriladi.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InputMediaPhoto

from services.database import Database

log = logging.getLogger(__name__)


def build_album(file_ids: list[str], caption: str) -> list[InputMediaPhoto]:
    """Albom: izoh faqat birinchi rasmda turadi (Telegram qoidasi)."""
    return [
        InputMediaPhoto(media=fid, caption=caption if i == 0 else None, parse_mode="HTML")
        for i, fid in enumerate(file_ids)
    ]


async def publish_album(bot: Bot, channel_id: Any, file_ids: list[str], caption: str) -> list[int]:
    messages = await bot.send_media_group(chat_id=channel_id, media=build_album(file_ids, caption))
    return [m.message_id for m in messages]


async def publish_photo(bot: Bot, channel_id: Any, file_id: str, caption: str) -> int:
    """Bitta rasmni izoh bilan alohida post qilib joylaydi. Telegram «sekinroq» desa, kutib qayta urinadi."""
    for attempt in range(3):
        try:
            message = await bot.send_photo(chat_id=channel_id, photo=file_id, caption=caption, parse_mode="HTML")
            return message.message_id
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            log.info("Telegram %s soniya kutishni so'radi", exc.retry_after)
            await asyncio.sleep(exc.retry_after + 1)
    raise RuntimeError("unreachable")


async def remove_product_posts(bot: Bot, db: Database, product_id: int) -> tuple[int, int]:
    """Mahsulotning kanaldagi barcha xabarlarini o'chiradi.

    Qaytaradi: (o'chirilganlar soni, o'chirib bo'lmaganlar soni).
    """
    messages = await db.get_channel_messages(product_id)
    deleted: list[int] = []
    failed = 0
    for chat_id, message_id in messages:
        chat: int | str = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        try:
            await bot.delete_message(chat_id=chat, message_id=message_id)
            deleted.append(message_id)
        except TelegramBadRequest as exc:
            # Xabar allaqachon o'chirilgan bo'lsa — o'chgan deb hisoblaymiz
            if "not found" in str(exc).lower():
                deleted.append(message_id)
            else:
                log.warning("Xabarni o'chirib bo'lmadi %s/%s: %s", chat_id, message_id, exc)
                failed += 1
        except TelegramAPIError as exc:
            log.warning("Xabarni o'chirib bo'lmadi %s/%s: %s", chat_id, message_id, exc)
            failed += 1
    if not failed:
        await db.mark_sold_out(product_id, deleted)
    return len(deleted), failed
