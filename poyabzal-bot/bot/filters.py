from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from config import Settings


class IsAdmin(Filter):
    """Faqat .env dagi ADMIN_ID ga ruxsat beradi."""

    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        user = event.from_user
        return bool(user and user.id == settings.admin_id)
