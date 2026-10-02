"""Asosiy ish: rasm(lar) + izoh → qayta ishlash → ko'rib chiqish → kanalga joylash.

Har bir rasm alohida mahsulot (masalan, bir modelning bir rangi) va kanalga alohida post
bo'lib chiqadi; izoh (tavsif) hammasida bir xil. Tasdiqlash tugmasi bitta — hammasi uchun.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import secrets

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.filters import IsAdmin
from bot.keyboards import BatchAction, ProductAction, confirm_keyboard
from config import Settings
from models.product import ParsedCaption, ProcessedPhoto, ProductImage, ProductStatus
from services.ai_service import AIService, build_channel_caption, format_money
from services.caption_parser import parse_caption
from services.channel_service import publish_photo
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


def _admin_summary(product_ids: list[int], parsed: ParsedCaption, notes: list[str]) -> str:
    count = len(product_ids)
    ids_text = f"#{product_ids[0]}" if count == 1 else f"#{product_ids[0]}–#{product_ids[-1]}"
    total_packs = (parsed.packs or 0) * count
    lines = [
        f"🧾 <b>{count} ta mahsulot ({ids_text})</b> — faqat siz ko'rasiz",
        "",
        f"👞 Brend: <b>{html.escape(parsed.brand or '')}</b>",
        f"🚚 Manba: {html.escape(parsed.source or 'yozilmagan')}",
    ]
    if count == 1:
        lines.append(f"📦 Pachka: {parsed.packs}")
    else:
        lines.append(f"📦 Har bir rasm (rang) uchun: {parsed.packs} pachka — jami {count} × {parsed.packs} = {total_packs} pachka")
    lines += [
        f"💵 Kelish: {format_money(parsed.cost_price)} so'm (1 pachka)",
        f"💰 Sotish: {format_money(parsed.sale_price)} so'm (1 pachka)",
    ]
    if parsed.cost_price and parsed.sale_price and parsed.packs:
        per_pack = parsed.sale_price - parsed.cost_price
        emoji = "📈" if per_pack >= 0 else "📉"
        lines.append(
            f"{emoji} Foyda: {format_money(per_pack)} so'm/pachka, "
            f"jami {format_money(per_pack * total_packs)} so'm"
        )
    elif not parsed.cost_price:
        lines.append("⚠️ Kelish narxi yozilmagan — foyda hisoblanmadi")
    if parsed.extra:
        lines.append(f"ℹ️ Qo'shimcha: {html.escape(parsed.extra)}")
    if notes:
        lines += ["", *[f"⚠️ {html.escape(n)}" for n in notes]]
    if count == 1:
        lines += ["", CONFIRM_QUESTION_ONE]
    else:
        lines += ["", CONFIRM_QUESTION_MANY.format(count=count)]
    return "\n".join(lines)


CONFIRM_QUESTION_ONE = "Yuqoridagi post kanalda aynan shunday ko'rinadi. Joylaymi?"
CONFIRM_QUESTION_MANY = (
    "Yuqoridagi {count} ta rasm kanalga {count} ta alohida post bo'lib chiqadi, "
    "har birida shu tavsif. Joylaymi?"
)


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

    status = await message.answer(
        f"⏳ {len(files)} ta rasm qayta ishlanmoqda (har biriga ~20–60 soniya)..."
    )
    batch_id = secrets.token_hex(4)
    product_ids: list[int] = []
    ai_task: asyncio.Task | None = None
    try:
        # Tavsif barcha rasmlar uchun bitta — uni rasm bilan parallel tayyorlaymiz
        ai_task = asyncio.create_task(ai.generate_description(parsed))

        processed: list[ProcessedPhoto] = []
        unreadable = 0
        for i, (file_id, _size) in enumerate(files, start=1):
            try:
                buffer = await bot.download(file_id)
                processed.append(await images.process(file_id, buffer.read()))
            except Exception:  # noqa: BLE001 — bitta buzuq rasm hammasini to'xtatmasin
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
        caption = build_channel_caption(description.text, settings.contact)

        # Har bir rasm — alohida mahsulot (rang) va alohida post
        for photo in processed:
            product_id = await db.create_product(shop_id, parsed, description.text, batch_id)
            product_ids.append(product_id)
            paths = await asyncio.to_thread(save_images, settings.images_dir, product_id, [photo.jpeg_bytes])
            await db.add_images(
                product_id,
                [ProductImage(product_id=product_id, position=0, original_file_id=photo.original_file_id, local_path=paths[0])],
            )
            preview = await bot.send_photo(
                chat_id=message.chat.id,
                photo=BufferedInputFile(photo.jpeg_bytes, filename=f"{product_id}.jpg"),
                caption=caption,
                parse_mode="HTML",
            )
            if preview.photo:
                await db.set_processed_file_ids(product_id, [preview.photo[-1].file_id])

        control = await message.answer(
            _admin_summary(product_ids, parsed, notes),
            reply_markup=confirm_keyboard(batch_id, len(product_ids)),
        )
        for product_id in product_ids:
            await db.set_preview_message(product_id, control.chat.id, control.message_id)
        await _safe_delete(status)
    except Exception:
        log.exception("Mahsulotni tayyorlashda xato")
        if ai_task is not None and not ai_task.done():
            ai_task.cancel()
        if product_ids:
            await db.cancel_batch(batch_id)
        await _safe_edit(
            status,
            "❌ Kutilmagan xato yuz berdi, mahsulot saqlanmadi. Iltimos, qaytadan yuboring.\n"
            "Xato takrorlansa, bot oynasidagi yozuvlarni tekshiring.",
        )


@router.callback_query(BatchAction.filter(F.action == "ok"))
async def on_confirm(
    callback: CallbackQuery, callback_data: BatchAction, bot: Bot, db: Database, settings: Settings
) -> None:
    product_ids = await db.start_publishing_batch(callback_data.batch_id)
    if not product_ids:
        await callback.answer("Bu postlar allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    await callback.answer(f"📤 {len(product_ids)} ta post kanalga joylanmoqda...")
    published: list[int] = []
    try:
        for product_id in product_ids:
            product = await db.get_product(product_id)
            imgs = await db.get_images(product_id)
            file_ids = [i.processed_file_id for i in imgs if i.processed_file_id]
            if not product or not file_ids:
                raise RuntimeError(f"#{product_id} rasmi bazada topilmadi")
            caption = build_channel_caption(product.description, settings.contact)
            message_id = await publish_photo(bot, settings.channel_id, file_ids[0], caption)
            await db.mark_published(product_id, settings.channel_id, [message_id])
            published.append(product_id)
            if len(product_ids) > 1:
                await asyncio.sleep(1)  # Telegram cheklovlariga tushmaslik uchun
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        await _revert_unpublished(db, product_ids, published)
        log.error("Kanalga joylab bo'lmadi: %s", exc)
        await _notify(
            callback,
            f"❌ Kanalga joylab bo'lmadi ({len(published)}/{len(product_ids)} ta joylandi).\n\n"
            "Tekshiring:\n• CHANNEL_ID to'g'ri yozilganmi\n"
            "• Bot kanalga <b>admin</b> qilib qo'shilganmi va «Xabar joylash» huquqi bormi\n\n"
            f"<i>Telegram javobi: {html.escape(str(exc))}</i>\n\n"
            "Tuzatgach, «Tasdiqlash» ni qayta bosing — qolganlari joylanadi.",
        )
        return
    except Exception:
        await _revert_unpublished(db, product_ids, published)
        log.exception("Kanalga joylashda xato")
        await _notify(
            callback,
            f"❌ Kutilmagan xato ({len(published)}/{len(product_ids)} ta joylandi). "
            "«Tasdiqlash» ni qayta bosing — qolganlari joylanadi.",
        )
        return

    batch = await db.list_batch(callback_data.batch_id)
    all_ids = [p.id for p in batch if p.status == ProductStatus.PUBLISHED]
    example = all_ids[0] if all_ids else product_ids[0]
    await _finish_control_message(
        callback,
        f"✅ <b>Kanalga joylandi!</b> ({', '.join(f'#{i}' for i in all_ids)})\n"
        f"Biror rang tugasa: <code>/tugadi {example}</code> (o'sha rangning raqami bilan)",
    )


@router.callback_query(BatchAction.filter(F.action == "no"))
async def on_cancel(callback: CallbackQuery, callback_data: BatchAction, db: Database) -> None:
    if await db.cancel_batch(callback_data.batch_id):
        await callback.answer("Bekor qilindi")
        await _finish_control_message(callback, "❌ <b>Bekor qilindi.</b> Kanalga joylanmadi.")
    else:
        await callback.answer("Bu postlar allaqachon ko'rib chiqilgan.", show_alert=True)


@router.callback_query(ProductAction.filter())
async def on_old_button(callback: CallbackQuery) -> None:
    await callback.answer("Bu tugma eskirgan. Rasmlarni qaytadan yuboring.", show_alert=True)


async def _revert_unpublished(db: Database, product_ids: list[int], published: list[int]) -> None:
    for product_id in product_ids:
        if product_id not in published:
            await db.revert_publishing(product_id)


# ---------- yordamchilar ----------

async def _finish_control_message(callback: CallbackQuery, footer: str) -> None:
    """Tugmalarni olib tashlab, natijani xabar oxiriga yozadi."""
    msg = callback.message
    if not isinstance(msg, Message):
        return
    base = msg.html_text or ""
    base = base.replace(CONFIRM_QUESTION_ONE, "")
    base = re.sub(r"Yuqoridagi \d+ ta rasm kanalga .*Joylaymi\?", "", base).rstrip()
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

