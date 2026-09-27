from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ProductAction(CallbackData, prefix="p"):
    action: str  # "ok" yoki "no"
    product_id: int


def confirm_keyboard(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data=ProductAction(action="ok", product_id=product_id))
    kb.button(text="❌ Bekor qilish", callback_data=ProductAction(action="no", product_id=product_id))
    kb.adjust(2)
    return kb.as_markup()
