"""Albomni (media group) bitta xabar sifatida yig'ish.

Telegram albomdagi har bir rasmni alohida xabar qilib yuboradi. Bu middleware
ularni qisqa vaqt kutib, bitta ro'yxatga yig'adi va handlerga `album` sifatida beradi.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AlbumMiddleware(BaseMiddleware):
    def __init__(self, latency: float = 1.2) -> None:
        self.latency = latency
        self._albums: dict[str, list[Message]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.media_group_id:
            if isinstance(event, Message):
                data["album"] = [event]
            return await handler(event, data)

        group_id = event.media_group_id
        if group_id in self._albums:
            self._albums[group_id].append(event)
            return None  # birinchi xabar hammasini birga ishlaydi

        self._albums[group_id] = [event]
        # Yangi rasmlar kelishdan to'xtaguncha kutamiz (sekin internet uchun)
        seen = 0
        while seen != len(self._albums[group_id]):
            seen = len(self._albums[group_id])
            await asyncio.sleep(self.latency)
        album = self._albums.pop(group_id)
        album.sort(key=lambda m: m.message_id)
        data["album"] = album
        return await handler(album[0], data)
