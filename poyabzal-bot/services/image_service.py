"""Rasm bilan ishlash: fonni olib tashlash va studiya fonini qo'yish.

Fon BiRefNet modeli bilan olib tashlanadi (bepul, MIT litsenziya, kompyuterning o'zida ishlaydi).
U rasmdagi asosiy predmetni ajratadi; keyin orqada qolgan mayda bo'laklar va boshqa
predmetlar (javondagi boshqa poyabzallar) tozalanadi — faqat asosiy mahsulot qoladi.

Natija: 1280x1280 JPEG, och gradient fon, yumshoq soya, mahsulot markazda.
Og'ir ish alohida oqimda (thread) bajariladi, bot qotib qolmaydi.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
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

# Modellar (hammasi bepul, kompyuterning o'zida ishlaydi):
#   birefnet-general       — eng sifatli: qo'l va orqadagi narsalarni ham olib tashlaydi;
#                            ~8 GB operativ xotira ishlatadi, bir rasmga ~30-60 soniya
#   birefnet-general-lite  — ~7 GB xotira, ~20 soniya; do'kon suratlarida sezilarli yomonroq
#   isnet-general-use      — ~1 GB xotira, ~2 soniya; faqat oddiy fonda yaxshi ishlaydi
# "auto" — xotira yetsa birefnet-general, aks holda isnet-general-use.
FALLBACK_MODEL = "isnet-general-use"
KEEP_RATIO = 0.25                      # eng katta bo'lakning 25% idan kichik bo'laklar o'chiriladi


class ImageService:
    def __init__(self, model_name: str = "auto", max_parallel: int = 1) -> None:
        self.model_name = pick_model(model_name)
        self._session = None
        self._session_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._background = self._make_background(CANVAS_SIZE)

    async def warmup(self) -> None:
        """Modelni oldindan yuklaydi (birinchi marta internetdan yuklab olinadi: 180 MB – 1 GB)."""
        await self._get_session()

    async def _get_session(self):
        async with self._session_lock:
            if self._session is None:
                from rembg import new_session  # og'ir import, faqat kerak bo'lganda

                log.info("Fon modeli yuklanmoqda: %s", self.model_name)
                try:
                    self._session = await asyncio.to_thread(new_session, self.model_name, sess_opts=_lean_options())
                except Exception:  # noqa: BLE001 — xotira yetmasa yoki yuklab bo'lmasa
                    if self.model_name == FALLBACK_MODEL:
                        raise
                    log.exception("%s modelini yuklab bo'lmadi, %s ishlatiladi", self.model_name, FALLBACK_MODEL)
                    self.model_name = FALLBACK_MODEL
                    self._session = await asyncio.to_thread(new_session, self.model_name, sess_opts=_lean_options())
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
        cutout = remove(source, session=session)
        if not isinstance(cutout, Image.Image):
            cutout = Image.open(io.BytesIO(cutout))
        cutout = cutout.convert("RGBA")
        cutout.putalpha(Image.fromarray(clean_alpha(np.array(cutout.getchannel("A")))))

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


def total_ram_gb() -> float:
    """Kompyuterdagi umumiy operativ xotira (GB). Aniqlab bo'lmasa 0."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1024**3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except Exception:  # noqa: BLE001
        return 0.0


def pick_model(requested: str) -> str:
    if requested and requested != "auto":
        return requested
    ram = total_ram_gb()
    model = "birefnet-general" if ram >= 11 else FALLBACK_MODEL
    log.info("Operativ xotira: %.1f GB — fon modeli: %s", ram, model)
    return model


def _lean_options():
    """Xotirani tejaydigan sozlamalar (katta modellar uchun muhim)."""
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.enable_cpu_mem_arena = False
    opts.enable_mem_pattern = False
    return opts


def clean_alpha(alpha: np.ndarray) -> np.ndarray:
    """Asosiy mahsulotni qoldirib, qolgan mayda bo'laklarni va chetdagi predmetlarni o'chiradi.

    Eng katta bo'lak (mahsulot) va unga yaqin kattalikdagi bo'laklar (masalan, juft poyabzalning
    ikkinchisi) qoladi; undan kichiklari — fon qoldiqlari — olib tashlanadi.
    """
    from scipy import ndimage

    solid = alpha > 32
    labels, count = ndimage.label(solid)
    if count <= 1:
        return alpha
    sizes = ndimage.sum(solid, labels, index=np.arange(1, count + 1))
    keep_ids = np.flatnonzero(sizes >= sizes.max() * KEEP_RATIO) + 1
    keep = np.isin(labels, keep_ids)
    # Yumshoq qirralarni yo'qotmaslik uchun saqlanadigan hududni biroz kengaytiramiz
    keep = ndimage.binary_dilation(keep, iterations=4)
    return np.where(keep, alpha, 0).astype(np.uint8)


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
