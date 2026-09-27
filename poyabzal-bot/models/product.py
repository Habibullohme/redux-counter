"""Ma'lumot modellari.

Bu yerdagi maydonlar bazadagi jadvallarga (models/schema_sqlite.sql) mos keladi.
Keyinchalik web sayt va Supabase ham xuddi shu tuzilmadan foydalanadi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProductStatus(str, Enum):
    PENDING = "pending"        # tasdiqlash kutilmoqda
    PUBLISHING = "publishing"  # kanalga joylanmoqda (ikki marta bosishdan himoya)
    PUBLISHED = "published"    # kanalda turibdi
    CANCELLED = "cancelled"    # admin bekor qildi
    SOLD_OUT = "sold_out"      # yuk tugadi, kanaldan o'chirildi


@dataclass
class ParsedCaption:
    """Admin yozgan izohdan ajratib olingan ma'lumot."""

    brand: str | None = None
    source: str | None = None        # Chorsu / Namangan
    packs: int | None = None         # nechta pachka bor
    cost_price: int | None = None    # kelish narxi (1 pachka) — MAXFIY
    sale_price: int | None = None    # sotish narxi (1 pachka)
    extra: str = ""                  # qo'shimcha (razmer, rang...) — kelish narxisiz
    raw: str = ""

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.brand:
            missing.append("Brend")
        if not self.packs:
            missing.append("pachka soni")
        if not self.sale_price:
            missing.append("sotish narxi")
        return missing


@dataclass
class Product:
    id: int
    shop_id: int
    brand: str
    source: str | None
    packs_total: int
    packs_sold: int
    cost_price: int | None
    sale_price: int
    currency: str
    extra_info: str
    raw_caption: str
    description: str
    status: ProductStatus
    created_at: str
    updated_at: str
    published_at: str | None = None
    barcode: str | None = None


@dataclass
class ProductImage:
    product_id: int
    position: int
    original_file_id: str
    processed_file_id: str | None = None
    local_path: str | None = None
    id: int | None = None


@dataclass
class ProcessedPhoto:
    """Qayta ishlangan rasm (hali bazaga yozilmagan)."""

    original_file_id: str
    jpeg_bytes: bytes
    background_removed: bool
    error: str | None = None
    extra: dict = field(default_factory=dict)
