"""Asosiy ish: rasm + izoh → qayta ishlash → ko'rib chiqish → kanalga joylash."""
from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from bot.filters import IsAdmin
from bot.keyboards import ProductAction, confirm_keyboard
from config import Settings
from models.product import ParsedCaption, ProcessedPhoto, ProductImage
from services.ai_service import AIService, build_channel_caption, format_money
from services.caption_parser import parse_caption
from services.channel_service import publish_album
from services.database import Database
from services.image_service import ImageService, save_images

log = logging.getLogger(__name__)

router = Router(name="products")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MAX_PHOTOS = 10  # Telegram albomida ko'pi bilan 10 ta rasm
MAX_FILE_SIZE = 20 * 1024 * 1024  # Bot API 20 MB dan katta faylni yuklab bera olmaydi

EXAMPLE = "<code>Brend: X, Chorsu, 10 pachka, kelish 150000, sotish 180000</code>"
IMAGE_FILTER = F.photo | (F.document & F.document.mime_type.startswith("image/"))


def _extract_file_ids(album: list[Message]) -> list[tuple[str, int | None]]:
    files: list[tuple[str, int | None]] = []
    for m in album:
        if m.photo:
            biggest = m.photo[-1]
            files.append((biggest.file_id, biggest.file_size))
        elif m.document and (m.document.mime_type or "").startswith("image/"):
            files.append((m.document.file_id, m.document.file_size))
    return files


def _find_caption(album: list[Message]) -> str:
    for m in album:
        if m.caption:
            return m.caption
    return ""


def _admin_summary(product_id: int, parsed: ParsedCaption, notes: list[str]) -> str:
    lines = [
        f"🧾 <b>Mahsulot #{product_id}</b> — faqat siz ko'rasiz",
        "",
        f"👞 Brend: <b>{html.escape(parsed.brand or '')}</b>",
        f"🚚 Manba: {html.escape(parsed.source or 'yozilmagan')}",
        f"📦 Pachka: {parsed.packs}",
        f"💵 Kelish: {format_money(parsed.cost_price)} so'm",
        f"💰 Sotish: {format_money(parsed.sale_price)} so'm",
    ]
    if parsed.cost_price and parsed.sale_price and parsed.packs:
        per_pack = parsed.sale_price - parsed.cost_price
        emoji = "📈" if per_pack >= 0 else "📉"
        lines.append(
            f"{emoji} Foyda: {format_money(per_pack)} so'm/pachka, "
            f"jami {format_money(per_pack * parsed.packs)} so'm"
        )
    elif not parsed.cost_price:
        lines.append("⚠️ Kelish narxi yozilmagan — foyda hisoblanmadi")
    if parsed.extra:
        lines.append(f"ℹ️ Qo'shimcha: {html.escape(parsed.extra)}")
    if notes:
        lines += ["", *[f"⚠️ {html.escape(n)}" for n in notes]]
    lines += ["", "Yuqoridagi albom kanalda aynan shunday ko'rinadi. Joylaymi?"]
    return "\n".join(lines)


@router.message(IMAGE_FILTER)
async def on_photos(
    message: Message,
    album: list[Message],
    bot: Bot,
    db: Database,
    images: ImageService,
    ai: AIService,
    settings: Settings,
    shop_id: int,
) -> None:
    parsed = parse_caption(_find_caption(album))
    missing = parsed.missing_fields()
    if missing:
        await message.reply(
            "✍️ Izohda quyidagilar yetishmayapti: <b>" + ", ".join(missing) + "</b>\n\n"
            f"Rasmlarni qaytadan yuboring va izohga shunday yozing:\n{EXAMPLE}"
        )
        return

    files = _extract_file_ids(album)
    notes: list[str] = []
    if len(files) > MAX_PHOTOS:
        notes.append(f"{len(files)} ta rasm keldi, faqat birinchi {MAX_PHOTOS} tasi olindi.")
        files = files[:MAX_PHOTOS]
    too_big = [f for f in files if f[1] and f[1] > MAX_FILE_SIZE]
    if too_big:
        notes.append(f"{len(too_big)} ta rasm 20 MB dan katta — tashlab ketildi.")
        files = [f for f in files if f not in too_big]
    if not files:
        await message.reply("Rasm topilmadi. Iltimos, rasm yuboring (20 MB gacha).")
        return

    status = await message.answer(f"⏳ {len(files)} ta rasm qayta ishlanmoqda va tavsif yozilmoqda...")
    product_id: int | None = None
    ai_task: asyncio.Task | None = None
    try:
        # AI tavsifini rasm bilan parallel boshlaymiz — vaqt tejaladi
        ai_task = asyncio.create_task(ai.generate_description(parsed))

        processed: list[ProcessedPhoto] = []
        unreadable = 0
        for i, (file_id, _size) in enumerate(files, start=1):
            try:
                buffer = await bot.download(file_id)
                processed.append(await images.process(file_id, buffer.read()))
            except Exception:  # noqa: BLE001 — bitta buzuq rasm butun albomni to'xtatmasin
                log.exception("Rasmni yuklab/ochib bo'lmadi: %s", file_id)
                unreadable += 1
            if len(files) > 1:
                await _safe_edit(status, f"⏳ Rasmlar: {i}/{len(files)} tayyor...")

        if not processed:
            ai_task.cancel()
            await _safe_edit(status, "❌ Rasmlarni ochib bo'lmadi. Boshqa rasm yuborib ko'ring.")
            return
        if unreadable:
            notes.append(f"{unreadable} ta rasmni ochib bo'lmadi — tashlab ketildi.")

        failed_bg = sum(1 for p in processed if not p.background_removed)
        if failed_bg:
            notes.append(f"{failed_bg} ta rasmda fonni olib bo'lmadi — asl rasm ishlatildi.")

        await _safe_edit(status, "✍️ Tavsif tayyorlanmoqda...")
        description = await ai_task
        if description.note:
            notes.append(description.note)

        # Bazaga yozish
        product_id = await db.create_product(shop_id, parsed, description.text)
        paths = await asyncio.to_thread(
            save_images, settings.images_dir, product_id, [p.jpeg_bytes for p in processed]
        )
        await db.add_images(
            product_id,
            [
                ProductImage(product_id=product_id, position=i, original_file_id=p.original_file_id, local_path=path)
                for i, (p, path) in enumerate(zip(processed, paths))
            ],
        )

        # Ko'rinishni adminga yuborish
        caption = build_channel_caption(description.text, settings.contact)
        media = [
            InputMediaPhoto(
                media=BufferedInputFile(p.jpeg_bytes, filename=f"{product_id}_{i + 1}.jpg"),
                caption=caption if i == 0 else None,
                parse_mode="HTML",
            )
            for i, p in enumerate(processed)
        ]
        preview = await bot.send_media_group(chat_id=message.chat.id, media=media)
        await db.set_processed_file_ids(product_id, [m.photo[-1].file_id for m in preview if m.photo])

        control = await message.answer(
            _admin_summary(product_id, parsed, notes), reply_markup=confirm_keyboard(product_id)
        )
        await db.set_preview_message(product_id, control.chat.id, control.message_id)
        await _safe_delete(status)
    except Exception:
        log.exception("Mahsulotni tayyorlashda xato")
        if ai_task is not None and not ai_task.done():
            ai_task.cancel()
        if product_id is not None:
            await db.cancel_product(product_id)
        await _safe_edit(
            status,
            "❌ Kutilmagan xato yuz berdi, mahsulot saqlanmadi. Iltimos, qaytadan yuboring.\n"
            "Xato takrorlansa, bot oynasidagi (terminal) yozuvlarni tekshiring.",
        )


@router.callback_query(ProductAction.filter(F.action == "ok"))
async def on_confirm(
    callback: CallbackQuery, callback_data: ProductAction, bot: Bot, db: Database, settings: Settings
) -> None:
    product_id = callback_data.product_id
    if not await db.try_start_publishing(product_id):
        product = await db.get_product(product_id)
        state = product.status.value if product else "topilmadi"
        await callback.answer(f"Bu mahsulot allaqachon ko'rib chiqilgan ({state}).", show_alert=True)
        return

    await callback.answer("📤 Kanalga joylanmoqda...")
    try:
        product = await db.get_product(product_id)
        imgs = await db.get_images(product_id)
        file_ids = [i.processed_file_id for i in imgs if i.processed_file_id]
        if not product or not file_ids:
            raise RuntimeError("Mahsulot rasmlari bazada topilmadi")

        caption = build_channel_caption(product.description, settings.contact)
        message_ids = await publish_album(bot, settings.channel_id, file_ids, caption)
        await db.mark_published(product_id, settings.channel_id, message_ids)
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        await db.revert_publishing(product_id)
        log.error("Kanalga joylab bo'lmadi: %s", exc)
        await _notify(
            callback,
            "❌ Kanalga joylab bo'lmadi.\n\n"
            "Tekshiring:\n• CHANNEL_ID to'g'ri yozilganmi\n"
            "• Bot kanalga <b>admin</b> qilib qo'shilganmi va «Xabar joylash» huquqi bormi\n\n"
            f"<i>Telegram javobi: {html.escape(str(exc))}</i>\n\nTuzatgach, «Tasdiqlash» ni qayta bosing.",
        )
        return
    except Exception:
        await db.revert_publishing(product_id)
        log.exception("Kanalga joylashda xato")
        await _notify(callback, "❌ Kutilmagan xato. «Tasdiqlash» ni qayta bosib ko'ring.")
        return

    await _finish_control_message(callback, f"✅ <b>Kanalga joylandi!</b> (#{product_id})\nYuk tugaganda: <code>/tugadi {product_id}</code>")


@router.callback_query(ProductAction.filter(F.action == "no"))
async def on_cancel(callback: CallbackQuery, callback_data: ProductAction, db: Database) -> None:
    if await db.cancel_product(callback_data.product_id):
        await callback.answer("Bekor qilindi")
        await _finish_control_message(callback, f"❌ <b>Bekor qilindi</b> (#{callback_data.product_id}). Kanalga joylanmadi.")
    else:
        await callback.answer("Bu mahsulot allaqachon ko'rib chiqilgan.", show_alert=True)


# ---------- yordamchilar ----------

async def _finish_control_message(callback: CallbackQuery, footer: str) -> None:
    """Tugmalarni olib tashlab, natijani xabar oxiriga yozadi."""
    msg = callback.message
    if not isinstance(msg, Message):
        return
    base = msg.html_text or ""
    base = base.replace("Yuqoridagi albom kanalda aynan shunday ko'rinadi. Joylaymi?", "").rstrip()
    try:
        await msg.edit_text(f"{base}\n\n{footer}", reply_markup=None)
    except TelegramAPIError:
        await msg.answer(footer)


async def _notify(callback: CallbackQuery, text: str) -> None:
    if isinstance(callback.message, Message):
        await callback.message.answer(text)


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except TelegramAPIError:
        pass


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramAPIError:
        pass

