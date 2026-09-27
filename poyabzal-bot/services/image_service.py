"""Rasm bilan ishlash: fonni olib tashlash (rembg) va studiya fonini qo'yish.

Natija: 1280x1280 JPEG, och gradient fon, yumshoq soya, mahsulot markazda.
rembg og'ir ish — u alohida oqimda (thread) bajariladi, bot qotib qolmaydi.
"""
from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from models.product import ProcessedPhoto

log = logging.getLogger(__name__)

CANVAS_SIZE = 1280
TOP_COLOR = (250, 250, 252)      # yuqori — deyarli oq
BOTTOM_COLOR = (226, 230, 236)   # pastki — och kulrang-ko'kish
MAX_PRODUCT_W = 0.80             # mahsulot kenglik bo'yicha maksimal ulushi
MAX_PRODUCT_H = 0.68             # balandlik bo'yicha maksimal ulushi


class ImageService:
    def __init__(self, model_name: str = "isnet-general-use", max_parallel: int = 1) -> None:
        self.model_name = model_name
        self._session = None
        self._session_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._background = self._make_background(CANVAS_SIZE)

    async def warmup(self) -> None:
        """Modelni oldindan yuklaydi (birinchi marta internetdan ~170 MB yuklab olinadi)."""
        await self._get_session()

    async def _get_session(self):
        async with self._session_lock:
            if self._session is None:
                from rembg import new_session  # og'ir import, faqat kerak bo'lganda

                log.info("rembg modeli yuklanmoqda: %s", self.model_name)
                self._session = await asyncio.to_thread(new_session, self.model_name)
            return self._session

    async def process(self, original_file_id: str, data: bytes) -> ProcessedPhoto:
        """Bitta rasmni qayta ishlaydi. Xato bo'lsa asl rasmni studiya foniga qo'yadi."""
        async with self._semaphore:
            try:
                session = await self._get_session()
                jpeg = await asyncio.to_thread(self._process_sync, data, session)
                return ProcessedPhoto(original_file_id, jpeg, background_removed=True)
            except Exception as exc:  # noqa: BLE001 — bot to'xtamasligi kerak
                log.exception("Fonni olib tashlashda xato")
                try:
                    jpeg = await asyncio.to_thread(self._fallback_sync, data)
                except Exception:  # rasm umuman ochilmasa
                    log.exception("Rasmni ochib bo'lmadi")
                    raise
                return ProcessedPhoto(original_file_id, jpeg, background_removed=False, error=str(exc))

    # ---------- sinxron (thread ichida) ----------

    def _process_sync(self, data: bytes, session) -> bytes:
        from rembg import remove

        source = self._open(data)
        cutout = remove(source, session=session, post_process_mask=True)
        if not isinstance(cutout, Image.Image):
            cutout = Image.open(io.BytesIO(cutout))
        cutout = cutout.convert("RGBA")

        bbox = cutout.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
        if not bbox:
            raise ValueError("Rasmda mahsulot topilmadi")
        cutout = cutout.crop(bbox)
        return self._compose(cutout)

    def _fallback_sync(self, data: bytes) -> bytes:
        """Fon olib tashlanmasa — asl rasmni o'zgartirmasdan studiya foni markaziga qo'yamiz."""
        img = self._open(data).convert("RGBA")
        return self._compose(img, with_shadow=False)

    @staticmethod
    def _open(data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # telefondagi burilishni to'g'rilash
        img.thumbnail((2000, 2000), Image.LANCZOS)
        return img.convert("RGBA")

    def _compose(self, product: Image.Image, with_shadow: bool = True) -> bytes:
        size = CANVAS_SIZE
        canvas = self._background.copy()

        # Mahsulotni o'lchamga keltirish
        scale = min(size * MAX_PRODUCT_W / product.width, size * MAX_PRODUCT_H / product.height)
        new_w, new_h = max(1, int(product.width * scale)), max(1, int(product.height * scale))
        product = product.resize((new_w, new_h), Image.LANCZOS)

        # Markazda, pastroqda (soya uchun joy)
        x = (size - new_w) // 2
        y = int(size * 0.53 - new_h / 2)
        floor_y = y + new_h

        if with_shadow:
            alpha = product.getchannel("A")

            # 1) Yerga tushgan yumshoq ellips soya
            contact = Image.new("L", (size, size), 0)
            ellipse_w, ellipse_h = int(new_w * 0.92), max(18, int(new_w * 0.09))
            ellipse = Image.new("L", (ellipse_w, ellipse_h), 0)
            ImageDraw.Draw(ellipse).ellipse((0, 0, ellipse_w - 1, ellipse_h - 1), fill=110)
            contact.paste(ellipse, ((size - ellipse_w) // 2, floor_y - ellipse_h // 2))
            contact = contact.filter(ImageFilter.GaussianBlur(radius=max(10, ellipse_h * 0.6)))
            canvas = Image.composite(Image.new("RGB", (size, size), (90, 95, 105)), canvas, contact)

            # 2) Mahsulot shaklidagi tarqoq soya (biroz pastga siljigan)
            drop = Image.new("L", (size, size), 0)
            drop.paste(alpha.point(lambda a: int(a * 0.28)), (x + int(new_w * 0.02), y + int(new_h * 0.04)))
            drop = drop.filter(ImageFilter.GaussianBlur(radius=max(12, size // 50)))
            canvas = Image.composite(Image.new("RGB", (size, size), (70, 75, 85)), canvas, drop)

        canvas.paste(product, (x, y), product)

        out = io.BytesIO()
        canvas.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
        return out.getvalue()

    @staticmethod
    def _make_background(size: int) -> Image.Image:
        """Vertikal och gradient + markazda yengil yorug'lik."""
        t = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]
        top = np.array(TOP_COLOR, dtype=np.float32)
        bottom = np.array(BOTTOM_COLOR, dtype=np.float32)
        grad = top + (bottom - top) * (t[..., None] ** 1.3)          # (size, 1, 3)
        grad = np.repeat(grad, size, axis=1)                          # (size, size, 3)

        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        cx, cy = size / 2, size * 0.45
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size * 0.75)
        glow = np.clip(1.0 - dist, 0.0, 1.0)[..., None] ** 2 * 10.0   # markaz yorug'roq
        vignette = np.clip(dist - 0.55, 0.0, 1.0)[..., None] * 18.0   # chetlar biroz to'qroq

        arr = np.clip(grad + glow - vignette, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGB")


def save_images(images_dir: Path, product_id: int, photos: list[bytes]) -> list[str]:
    """Qayta ishlangan rasmlarni diskka saqlaydi (keyin sayt/Supabase Storage uchun)."""
    folder = images_dir / str(product_id)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, data in enumerate(photos):
        path = folder / f"{i + 1}.jpg"
        path.write_bytes(data)
        paths.append(str(path))
    return paths
