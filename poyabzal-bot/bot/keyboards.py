from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class BatchAction(CallbackData, prefix="b"):
    """Bitta tasdiq bir vaqtda yuborilgan barcha rasmlarga tegishli."""

    action: str  # "ok" yoki "no"
    batch_id: str


class ProductAction(CallbackData, prefix="p"):
    """Eski versiyadagi tugmalar (faqat «eskirgan» deb javob berish uchun)."""

    action: str
    product_id: int


def confirm_keyboard(batch_id: str, count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    label = "✅ Tasdiqlash" if count == 1 else f"✅ Tasdiqlash ({count} ta post)"
    kb.button(text=label, callback_data=BatchAction(action="ok", batch_id=batch_id))
    kb.button(text="❌ Bekor qilish", callback_data=BatchAction(action="no", batch_id=batch_id))
    kb.adjust(1)
    return kb.as_markup()
