"""Oddiy buyruqlar: /start, /yordam, /mahsulotlar, /tugadi."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.filters import IsAdmin
from models.product import ProductStatus
from services.ai_service import format_money
from services.channel_service import remove_product_posts
from services.database import Database

router = Router(name="common")
router.message.filter(IsAdmin())

HELP_TEXT = (
    "👋 <b>Assalomu alaykum!</b>\n\n"
    "Menga mahsulot rasmlarini yuboring (bitta yoki bir nechtasini birga, 10 tagacha) va "
    "<b>izohga</b> ma'lumotni yozing. Masalan:\n\n"
    "<code>Brend: Baldinini, Chorsu, 10 pachka, kelish 150000, sotish 180000</code>\n\n"
    "Qo'shimcha yozsangiz ham bo'ladi: <code>razmer 39-44, pachkada 6 juft</code>\n\n"
    "Men:\n"
    "1️⃣ Rasmlar fonini olib, chiroyli studiya foniga qo'yaman\n"
    "2️⃣ Xaridorlar uchun tavsif yozaman (kelish narxi kanalga CHIQMAYDI)\n"
    "3️⃣ Sizga ko'rsataman — «Tasdiqlash» bossangiz, <b>har bir rasmni alohida post</b> qilib kanalga joylayman\n\n"
    "📦 Bir modelning bir nechta rangini yuborsangiz, pachka soni <b>har bir rang uchun</b> hisoblanadi.\n"
    "📸 Fon yaxshi tozalanishi uchun poyabzalni qo'lda ushlamay, oddiy fonda suratga oling.\n\n"
    "<b>Buyruqlar:</b>\n"
    "/mahsulotlar — oxirgi mahsulotlar va raqamlari\n"
    "/tugadi 12 — 12-raqamli mahsulot (rang) tugadi, kanaldan o'chirish\n"
    "/yordam — shu yordam"
)

STATUS_LABELS = {
    ProductStatus.PENDING: "⏳ tasdiq kutmoqda",
    ProductStatus.PUBLISHING: "📤 joylanmoqda",
    ProductStatus.PUBLISHED: "✅ kanalda",
    ProductStatus.CANCELLED: "❌ bekor qilingan",
    ProductStatus.SOLD_OUT: "🏁 tugagan",
}


@router.message(CommandStart())
@router.message(Command("yordam", "help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("mahsulotlar"))
async def cmd_products(message: Message, db: Database, shop_id: int) -> None:
    products = await db.list_products(shop_id, limit=20)
    if not products:
        await message.answer("Hali mahsulot yo'q. Rasm yuborib boshlang 🙂")
        return
    lines = ["<b>Oxirgi mahsulotlar:</b>\n"]
    for p in products:
        lines.append(
            f"<b>#{p.id}</b> {html.escape(p.brand)} — {p.packs_total} pachka, "
            f"{format_money(p.sale_price)} so'm · {STATUS_LABELS.get(p.status, p.status.value)}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("tugadi"))
async def cmd_sold_out(message: Message, command: CommandObject, bot: Bot, db: Database, shop_id: int) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdigit():
        await message.answer("Mahsulot raqamini yozing, masalan: <code>/tugadi 12</code>\nRaqamlarni /mahsulotlar da ko'rasiz.")
        return
    product = await db.get_product(int(arg))
    if not product or product.shop_id != shop_id:
        await message.answer("Bunday raqamli mahsulot topilmadi.")
        return
    if product.status != ProductStatus.PUBLISHED:
        await message.answer(f"#{product.id} kanalda emas ({STATUS_LABELS.get(product.status)}).")
        return
    deleted, failed = await remove_product_posts(bot, db, product.id)
    if failed:
        await message.answer(
            f"⚠️ {deleted} ta xabar o'chirildi, {failed} tasini o'chirib bo'lmadi.\n"
            "Bot kanalda «xabarlarni o'chirish» huquqiga ega ekanini tekshiring. "
            "Telegram 48 soatdan eski xabarlarni o'chirishga ruxsat bermasligi ham mumkin."
        )
    else:
        await message.answer(f"🏁 #{product.id} ({html.escape(product.brand)}) kanaldan o'chirildi va «tugagan» deb belgilandi.")


@router.message(F.text)
async def text_without_photo(message: Message) -> None:
    await message.answer(
        "📸 Avval rasm yuboring, ma'lumotni esa rasmning <b>izohiga</b> yozing.\n"
        "Batafsil: /yordam"
    )


# ---------- begonalar uchun ----------

stranger_router = Router(name="stranger")


@stranger_router.message(F.chat.type == "private")
async def stranger_message(message: Message) -> None:
    await message.answer("⛔ Bu bot faqat do'kon egasi uchun.")


@stranger_router.callback_query()
async def stranger_callback(callback: CallbackQuery) -> None:
    await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
