"""Sozlamalar: barcha maxfiy ma'lumotlar .env faylidan o'qiladi.

Kodga hech qanday token yoki kalit yozilmaydi.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_id: int | str
    admin_id: int
    anthropic_api_key: str
    claude_model: str
    shop_name: str
    contact: str
    rembg_model: str
    database_path: Path
    images_dir: Path


def _fail(message: str) -> None:
    print(f"\n[XATO] {message}\n.env faylini tekshiring (README.md ga qarang).\n", file=sys.stderr)
    sys.exit(1)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or "..." in value or "bu-yerga" in value:
        _fail(f"{name} .env faylida to'ldirilmagan.")
    return value


def _parse_channel_id(raw: str) -> int | str:
    # "-1001234567890" -> int, "@kanalim" -> str
    if raw.lstrip("-").isdigit():
        return int(raw)
    if not raw.startswith("@"):
        raw = "@" + raw
    return raw


def load_settings() -> Settings:
    admin_raw = _required("ADMIN_ID")
    if not admin_raw.isdigit():
        _fail("ADMIN_ID faqat raqamlardan iborat bo'lishi kerak (masalan 123456789).")

    db_path = Path(os.getenv("DATABASE_PATH", "data/shop.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    return Settings(
        bot_token=_required("BOT_TOKEN"),
        channel_id=_parse_channel_id(_required("CHANNEL_ID")),
        admin_id=int(admin_raw),
        anthropic_api_key=_required("ANTHROPIC_API_KEY"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5").strip() or "claude-sonnet-5",
        shop_name=os.getenv("SHOP_NAME", "Poyabzal Optom").strip(),
        contact=os.getenv("CONTACT", "").strip(),
        rembg_model=os.getenv("REMBG_MODEL", "isnet-general-use").strip() or "isnet-general-use",
        database_path=db_path,
        images_dir=db_path.parent / "images",
    )
