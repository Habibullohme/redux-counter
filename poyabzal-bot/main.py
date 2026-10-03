"""Botni ishga tushirish: python main.py"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent

from bot.handlers import common, products
from bot.middlewares import AlbumMiddleware
from config import load_settings
from services.ai_service import AIService, build_provider
from services.database import Database
from services.image_service import ImageService


def setup_logging(log_path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    file = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[console, file])
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.database_path.parent / "bot.log")
    log = logging.getLogger("main")

    db = Database(settings.database_path)
    await db.init()
    shop_id = await db.get_or_create_shop(settings.admin_id, settings.shop_name, settings.channel_id)

    images = ImageService(settings.rembg_model, settings.photo_style)
    provider = build_provider(
        settings.ai_provider,
        settings.gemini_api_key, settings.gemini_model,
        settings.anthropic_api_key, settings.claude_model,
    )
    ai = AIService(provider, template_only=settings.ai_provider == "none")
    if settings.ai_provider == "none":
        log.info("Tavsiflar shablon bo'yicha yoziladi (AI_PROVIDER=none)")
    elif provider is None:
        log.warning("AI kaliti yo'q (%s) — tavsiflar shablon bo'yicha yoziladi", settings.ai_provider)
    else:
        log.info("Tavsif yozuvchi AI: %s (%s)", provider.name, provider.model)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(settings=settings, db=db, images=images, ai=ai, shop_id=shop_id)
    dp.message.middleware(AlbumMiddleware())

    dp.include_router(products.router)
    dp.include_router(common.router)
    dp.include_router(common.stranger_router)  # oxirida: admin bo'lmaganlar

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        # Har qanday kutilmagan xato shu yerga tushadi — bot to'xtamaydi
        log.exception("Kutilmagan xato: %s", event.exception, exc_info=event.exception)
        try:
            await bot.send_message(settings.admin_id, "⚠️ Botda xato yuz berdi, lekin bot ishlashda davom etyapti.")
        except Exception:  # noqa: BLE001
            pass
        return True

    try:
        me = await bot.get_me()
        log.info("Bot ishga tushdi: @%s", me.username)
        await bot.set_my_commands([
            BotCommand(command="start", description="Boshlash"),
            BotCommand(command="mahsulotlar", description="Oxirgi mahsulotlar"),
            BotCommand(command="tugadi", description="Yuk tugadi — kanaldan o'chirish"),
            BotCommand(command="yordam", description="Yordam"),
        ])
        log.info("Rasm modeli tayyorlanmoqda (birinchi safar bir necha daqiqa olishi mumkin)...")
        try:
            await images.warmup()
        except Exception:  # noqa: BLE001 — model keyin, birinchi rasmda qayta yuklanadi
            log.exception("Rasm modelini yuklab bo'lmadi (internetni tekshiring)")
        log.info("Tayyor! Botga rasm yuborishingiz mumkin.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi.")
