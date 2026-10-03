"""SQLite bilan ishlash (repository qatlami).

Bot kodining qolgan qismi faqat shu klass metodlarini chaqiradi. Keyinchalik
Supabase ga o'tganda faqat shu faylni almashtirish kifoya bo'ladi.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from models.product import ParsedCaption, Product, ProductImage, ProductStatus

T = TypeVar("T")
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "models" / "schema_sqlite.sql"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    # ---------- ichki yordamchilar ----------

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    async def _run(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        def wrapper() -> T:
            with self._lock:
                assert self._conn is not None, "Database.init() chaqirilmagan"
                try:
                    result = fn(self._conn)
                    self._conn.commit()
                    return result
                except Exception:
                    self._conn.rollback()
                    raise

        return await asyncio.to_thread(wrapper)

    # ---------- ishga tushirish ----------

    async def init(self) -> None:
        self._conn = await asyncio.to_thread(self._connect)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        await self._run(lambda c: c.executescript(schema))
        await self._run(_migrate)

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            await asyncio.to_thread(conn.close)

    async def get_or_create_shop(self, owner_telegram_id: int, name: str, channel_id: Any) -> int:
        def q(c: sqlite3.Connection) -> int:
            row = c.execute(
                "SELECT id FROM shops WHERE owner_telegram_id = ? ORDER BY id LIMIT 1",
                (owner_telegram_id,),
            ).fetchone()
            if row:
                c.execute(
                    "UPDATE shops SET name = ?, channel_id = ? WHERE id = ?",
                    (name, str(channel_id), row["id"]),
                )
                return int(row["id"])
            cur = c.execute(
                "INSERT INTO shops (name, owner_telegram_id, channel_id, created_at) VALUES (?, ?, ?, ?)",
                (name, owner_telegram_id, str(channel_id), _now()),
            )
            return int(cur.lastrowid)

        return await self._run(q)

    # ---------- mahsulotlar ----------

    async def create_product(
        self, shop_id: int, parsed: ParsedCaption, description: str, batch_id: str | None = None
    ) -> int:
        def q(c: sqlite3.Connection) -> int:
            now = _now()
            cur = c.execute(
                """INSERT INTO products (shop_id, batch_id, brand, source, packs_total, cost_price, sale_price,
                       extra_info, raw_caption, description, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    shop_id, batch_id, parsed.brand, parsed.source, parsed.packs, parsed.cost_price,
                    parsed.sale_price, parsed.extra, parsed.raw, description,
                    ProductStatus.PENDING.value, now, now,
                ),
            )
            return int(cur.lastrowid)

        return await self._run(q)

    async def add_images(self, product_id: int, images: list[ProductImage]) -> None:
        def q(c: sqlite3.Connection) -> None:
            now = _now()
            c.executemany(
                """INSERT INTO product_images (product_id, position, original_file_id,
                       processed_file_id, local_path, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (product_id, i.position, i.original_file_id, i.processed_file_id, i.local_path, now)
                    for i in images
                ],
            )

        await self._run(q)

    async def set_processed_file_ids(self, product_id: int, file_ids: list[str]) -> None:
        def q(c: sqlite3.Connection) -> None:
            for position, file_id in enumerate(file_ids):
                c.execute(
                    "UPDATE product_images SET processed_file_id = ? WHERE product_id = ? AND position = ?",
                    (file_id, product_id, position),
                )

        await self._run(q)

    async def set_preview_message(self, product_id: int, chat_id: int, message_id: int) -> None:
        await self._run(
            lambda c: c.execute(
                "UPDATE products SET preview_chat_id = ?, preview_message_id = ?, updated_at = ? WHERE id = ?",
                (chat_id, message_id, _now(), product_id),
            )
        )

    async def get_product(self, product_id: int) -> Product | None:
        def q(c: sqlite3.Connection) -> Product | None:
            row = c.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            return _row_to_product(row) if row else None

        return await self._run(q)

    async def get_images(self, product_id: int) -> list[ProductImage]:
        def q(c: sqlite3.Connection) -> list[ProductImage]:
            rows = c.execute(
                "SELECT * FROM product_images WHERE product_id = ? ORDER BY position", (product_id,)
            ).fetchall()
            return [
                ProductImage(
                    id=r["id"], product_id=r["product_id"], position=r["position"],
                    original_file_id=r["original_file_id"], processed_file_id=r["processed_file_id"],
                    local_path=r["local_path"],
                )
                for r in rows
            ]

        return await self._run(q)

    async def list_products(self, shop_id: int, limit: int = 10) -> list[Product]:
        def q(c: sqlite3.Connection) -> list[Product]:
            rows = c.execute(
                "SELECT * FROM products WHERE shop_id = ? ORDER BY id DESC LIMIT ?", (shop_id, limit)
            ).fetchall()
            return [_row_to_product(r) for r in rows]

        return await self._run(q)

    async def list_batch(self, batch_id: str) -> list[Product]:
        def q(c: sqlite3.Connection) -> list[Product]:
            rows = c.execute("SELECT * FROM products WHERE batch_id = ? ORDER BY id", (batch_id,)).fetchall()
            return [_row_to_product(r) for r in rows]

        return await self._run(q)

    async def start_publishing_batch(self, batch_id: str) -> list[int]:
        """Guruhdagi kutilayotgan mahsulotlarni 'publishing' ga o'tkazadi va ularning ID larini qaytaradi.

        Butun amal bitta qulf ichida bajariladi, shuning uchun tugma ikki marta bosilsa,
        ikkinchi bosish bo'sh ro'yxat oladi.
        """

        def q(c: sqlite3.Connection) -> list[int]:
            ids = [
                int(r["id"])
                for r in c.execute(
                    "SELECT id FROM products WHERE batch_id = ? AND status = ? ORDER BY id",
                    (batch_id, ProductStatus.PENDING.value),
                ).fetchall()
            ]
            now = _now()
            c.executemany(
                "UPDATE products SET status = ?, updated_at = ? WHERE id = ?",
                [(ProductStatus.PUBLISHING.value, now, i) for i in ids],
            )
            return ids

        return await self._run(q)

    async def cancel_batch(self, batch_id: str) -> int:
        def q(c: sqlite3.Connection) -> int:
            cur = c.execute(
                "UPDATE products SET status = ?, updated_at = ? WHERE batch_id = ? AND status = ?",
                (ProductStatus.CANCELLED.value, _now(), batch_id, ProductStatus.PENDING.value),
            )
            return cur.rowcount

        return await self._run(q)

    async def _change_status(self, product_id: int, from_status: ProductStatus, to_status: ProductStatus) -> bool:
        """Holatni faqat kutilgan holatda bo'lsa o'zgartiradi (ikki marta bosishdan himoya)."""

        def q(c: sqlite3.Connection) -> bool:
            cur = c.execute(
                "UPDATE products SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (to_status.value, _now(), product_id, from_status.value),
            )
            return cur.rowcount == 1

        return await self._run(q)

    async def try_start_publishing(self, product_id: int) -> bool:
        return await self._change_status(product_id, ProductStatus.PENDING, ProductStatus.PUBLISHING)

    async def revert_publishing(self, product_id: int) -> None:
        await self._change_status(product_id, ProductStatus.PUBLISHING, ProductStatus.PENDING)

    async def cancel_product(self, product_id: int) -> bool:
        return await self._change_status(product_id, ProductStatus.PENDING, ProductStatus.CANCELLED)

    async def mark_published(self, product_id: int, chat_id: Any, message_ids: list[int]) -> None:
        def q(c: sqlite3.Connection) -> None:
            now = _now()
            c.executemany(
                "INSERT INTO channel_messages (product_id, chat_id, message_id, created_at) VALUES (?, ?, ?, ?)",
                [(product_id, str(chat_id), mid, now) for mid in message_ids],
            )
            c.execute(
                "UPDATE products SET status = ?, published_at = ?, updated_at = ? WHERE id = ?",
                (ProductStatus.PUBLISHED.value, now, now, product_id),
            )

        await self._run(q)

    async def get_channel_messages(self, product_id: int) -> list[tuple[str, int]]:
        def q(c: sqlite3.Connection) -> list[tuple[str, int]]:
            rows = c.execute(
                "SELECT chat_id, message_id FROM channel_messages WHERE product_id = ? AND deleted_at IS NULL",
                (product_id,),
            ).fetchall()
            return [(r["chat_id"], int(r["message_id"])) for r in rows]

        return await self._run(q)

    async def mark_sold_out(self, product_id: int, deleted_message_ids: list[int]) -> None:
        def q(c: sqlite3.Connection) -> None:
            now = _now()
            c.executemany(
                "UPDATE channel_messages SET deleted_at = ? WHERE product_id = ? AND message_id = ?",
                [(now, product_id, mid) for mid in deleted_message_ids],
            )
            c.execute(
                "UPDATE products SET status = ?, updated_at = ? WHERE id = ?",
                (ProductStatus.SOLD_OUT.value, now, product_id),
            )

        await self._run(q)


def _migrate(c: sqlite3.Connection) -> None:
    """Eski bazaga yangi ustunlarni qo'shadi (ma'lumot o'chmaydi)."""
    columns = {r["name"] for r in c.execute("PRAGMA table_info(products)").fetchall()}
    if "batch_id" not in columns:
        c.execute("ALTER TABLE products ADD COLUMN batch_id TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_batch ON products(batch_id)")


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"], shop_id=row["shop_id"], brand=row["brand"], source=row["source"],
        packs_total=row["packs_total"], packs_sold=row["packs_sold"], cost_price=row["cost_price"],
        sale_price=row["sale_price"], currency=row["currency"], extra_info=row["extra_info"],
        raw_caption=row["raw_caption"], description=row["description"],
        status=ProductStatus(row["status"]), created_at=row["created_at"],
        updated_at=row["updated_at"], published_at=row["published_at"], barcode=row["barcode"],
        batch_id=row["batch_id"],
    )
