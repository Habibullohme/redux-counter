"""Rasm bilan ishlash. Uslublar (.env dagi PHOTO_STYLE):

- portrait (standart): iPhone «portret/fokus» rejimidagidek. Har bir nuqtaning kameragacha
  masofasi (chuqurlik) aniqlanadi: mahsulot va uni ushlagan qo'l tiniq qoladi, orqadagi
  javonlar esa uzoqligiga qarab obyektiv kabi (yumaloq «bokeh» bilan) xiralashadi.
- blur: mahsulot niqobi bo'yicha oddiy xiralashtirish (eski uslub).
- studio: fon butunlay olib tashlanib, och gradientli studiya foni qo'yiladi.

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
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

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


BLUR_LONG_SIDE = 1600           # blur uslubida natijaning uzun tomoni (piksel)


class ImageService:
    def __init__(self, model_name: str = "auto", style: str = "portrait", max_parallel: int = 1) -> None:
        self.style = style if style in ("portrait", "blur", "studio") else "portrait"
        # Portret uslubida asosiy ishni chuqurlik modeli qiladi — yengil niqob modeli yetarli
        if self.style == "portrait" and model_name in ("", "auto"):
            model_name = FALLBACK_MODEL
        self.model_name = pick_model(model_name)
        self._depth = None
        self._session = None
        self._session_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._background = self._make_background(CANVAS_SIZE)

    async def warmup(self) -> None:
        """Modellarni oldindan yuklaydi (birinchi marta internetdan yuklab olinadi)."""
        await self._get_session()
        if self.style == "portrait":
            await self._get_depth()

    async def _get_depth(self):
        async with self._session_lock:
            if self._depth is None:
                from services.depth import DepthEstimator

                log.info("Chuqurlik modeli yuklanmoqda (birinchi safar ~100 MB)")
                self._depth = await asyncio.to_thread(DepthEstimator)
            return self._depth

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
                depth = await self._get_depth() if self.style == "portrait" else None
                jpeg = await asyncio.to_thread(self._process_sync, data, session, depth)
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

    def _process_sync(self, data: bytes, session, depth=None) -> bytes:
        from rembg import remove

        source = self._open(data)
        cutout = remove(source, session=session)
        if not isinstance(cutout, Image.Image):
            cutout = Image.open(io.BytesIO(cutout))
        cutout = cutout.convert("RGBA")
        alpha = clean_alpha(np.array(cutout.getchannel("A")))
        if self.style == "portrait" and depth is not None:
            return portrait_blur(source, depth.predict(source), alpha)
        if self.style == "blur":
            return blur_background(source, alpha)
        cutout.putalpha(Image.fromarray(alpha))

        bbox = cutout.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
        if not bbox:
            raise ValueError("Rasmda mahsulot topilmadi")
        cutout = cutout.crop(bbox)
        return self._compose(cutout)

    def _fallback_sync(self, data: bytes) -> bytes:
        """Mahsulotni aniqlab bo'lmasa: blur uslubida butun rasm tiniqlashtiriladi,
        studio uslubida asl rasm studiya foni markaziga qo'yiladi."""
        img = self._open(data)
        if self.style in ("portrait", "blur"):
            return _to_jpeg(_limit_size(_enhance(img.convert("RGB"))))
        return self._compose(img.convert("RGBA"), with_shadow=False)

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


def _enhance(img: Image.Image) -> Image.Image:
    """Mahsulotni tiniqlashtirish: keskinlik, biroz kontrast va rang."""
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=90, threshold=2))
    img = ImageEnhance.Contrast(img).enhance(1.06)
    return ImageEnhance.Color(img).enhance(1.05)


def _limit_size(img: Image.Image) -> Image.Image:
    img = img.copy()
    img.thumbnail((BLUR_LONG_SIDE, BLUR_LONG_SIDE), Image.LANCZOS)
    return img


def _to_jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()


def blur_background(source: Image.Image, alpha: np.ndarray) -> bytes:
    """Mahsulot tiniq, orqa fon «portret rejimi»dagidek xira."""
    img = source.convert("RGB")
    if alpha.max() == 0:
        return _to_jpeg(_limit_size(_enhance(img)))
    w, h = img.size

    # Mahsulot niqobi: chetlarini biroz kengaytirib, yumshatamiz
    mask = Image.fromarray(alpha).filter(ImageFilter.MaxFilter(5))
    mask = mask.filter(ImageFilter.GaussianBlur(max(2, max(w, h) // 400)))
    m = np.asarray(mask, dtype=np.float32)[..., None] / 255.0

    # Fon: mahsulotni chiqarib tashlab xiralashtiramiz — shunda mahsulot atrofida qora «halo» bo'lmaydi
    radius = max(8, int(max(w, h) * 0.022))
    arr = np.asarray(img, dtype=np.float32)
    bg_weight = 1.0 - m
    num = Image.fromarray(np.clip(arr * bg_weight, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))
    den = Image.fromarray((bg_weight[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))
    num_a = np.asarray(num, dtype=np.float32)
    den_a = np.asarray(den, dtype=np.float32)[..., None] / 255.0
    plain = np.asarray(img.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    bg = np.where(den_a > 0.05, num_a / np.maximum(den_a, 0.05), plain)
    bg = bg * 0.85 + 255 * 0.09                      # fon biroz yorug'roq — mahsulot ajralib turadi
    gray = bg.mean(axis=2, keepdims=True)
    bg = bg * 0.8 + gray * 0.2                       # fon ranglari biroz so'nadi

    fg = np.asarray(_enhance(img), dtype=np.float32)
    out = np.clip(fg * m + bg * (1.0 - m), 0, 255).astype(np.uint8)
    return _to_jpeg(_limit_size(Image.fromarray(out)))


def _guided_filter(guide: np.ndarray, src: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Niqob chegaralarini rasmdagi haqiqiy chegaralarga moslaydi (soch/ip kabi mayda joylar ham)."""
    from scipy import ndimage

    def mean(x: np.ndarray) -> np.ndarray:
        return ndimage.uniform_filter(x, size=2 * radius + 1, mode="reflect")

    mean_i, mean_p = mean(guide), mean(src)
    a = (mean(guide * src) - mean_i * mean_p) / (mean(guide * guide) - mean_i * mean_i + eps)
    b = mean_p - a * mean_i
    return mean(a) * guide + mean(b)


def _disc_kernel(radius: int) -> np.ndarray:
    y, x = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    kernel = ((x * x + y * y) <= radius * radius).astype(np.float32)
    return kernel / kernel.sum()


def _lens_blur(linear: np.ndarray, weight: np.ndarray, radius: int) -> tuple[np.ndarray, np.ndarray]:
    """Obyektiv xiraligi (doira shaklidagi «bokeh»). Faqat `weight` > 0 joylar hisobga olinadi."""
    from scipy.signal import fftconvolve

    kernel = _disc_kernel(radius)
    num = np.stack([fftconvolve(linear[..., c] * weight, kernel, mode="same") for c in range(3)], axis=-1)
    den = fftconvolve(weight, kernel, mode="same")[..., None]
    return num, den


def _product_matte(gray: np.ndarray, seg: np.ndarray) -> np.ndarray:
    """Mahsulot niqobini aniq chegarali qiladi (ichi to'liq 1, chekkasi 1-2 piksel yumshoq)."""
    from scipy import ndimage

    solid = seg > 0.5
    labels, count = ndimage.label(solid)
    if count == 0:
        return np.zeros_like(gray)
    sizes = ndimage.sum(solid, labels, index=np.arange(1, count + 1))
    solid = labels == (int(np.argmax(sizes)) + 1)
    solid = ndimage.binary_fill_holes(solid)
    # Chegarani rasmdagi haqiqiy chetga moslash (kichik radius — faqat chekka atrofida)
    matte = _guided_filter(gray, solid.astype(np.float32), 2, 1e-4)
    matte = np.clip((matte - 0.25) / 0.5, 0, 1)
    # Ichki qism albatta to'liq tiniq
    inner = ndimage.binary_erosion(solid, iterations=2)
    return np.maximum(matte, inner.astype(np.float32))


def portrait_blur(source: Image.Image, depth: np.ndarray, alpha: np.ndarray) -> bytes:
    """iPhone portret rejimi: fokusdagi narsalar tiniq, orqasi uzoqligiga qarab xira."""
    img = _limit_size(source.convert("RGB"))
    w, h = img.size
    if depth.shape != (h, w):
        depth = np.asarray(Image.fromarray(depth.astype(np.float32)).resize((w, h), Image.BILINEAR), dtype=np.float32)
    if alpha.shape != (h, w):
        alpha = np.asarray(Image.fromarray(alpha).resize((w, h), Image.BILINEAR))
    rgb = np.asarray(img, dtype=np.float32) / 255.0
    seg = alpha.astype(np.float32) / 255.0

    # Fokus chuqurligi: markazdagi mahsulot (niqob bo'lsa — markazdagi niqob qismi)
    y0, y1, x0, x1 = int(h * 0.25), int(h * 0.7), int(w * 0.25), int(w * 0.75)
    center = depth[y0:y1, x0:x1]
    center_seg = seg[y0:y1, x0:x1] > 0.5
    focus_depth = float(np.percentile(center[center_seg] if center_seg.sum() > 500 else center, 75))

    diff = depth - focus_depth  # musbat — kameraga yaqinroq (qo'l), manfiy — uzoqroq (javon)
    near_ok, far_tol, soft = 0.30, 0.07, 0.10
    focus = np.where(
        diff >= 0,
        np.clip(1 - (diff - near_ok) / soft, 0, 1),
        np.clip(1 - (-diff - far_tol) / soft, 0, 1),
    )
    gray = rgb.mean(axis=-1)
    focus = _guided_filter(gray, focus.astype(np.float32), max(4, w // 120), 1e-3)
    focus = np.clip((focus - 0.15) / 0.7, 0, 1)

    # Poyabzalning o'zi: aniq, qattiq chegarali niqob. Uning ichida xiralik umuman bo'lmaydi,
    # chegarasi esa 1-2 piksel ichida rasmdagi haqiqiy chetga moslashtiriladi.
    shoe = _product_matte(gray, seg * (diff > -0.22))
    focus = np.maximum(focus, shoe)

    farness = np.clip((-diff - far_tol) / 0.35, 0, 1)[..., None]
    linear = rgb ** 2.2  # yorug' nuqtalar haqiqiy obyektivdagidek yorqin «bokeh» beradi
    radius = max(10, int(max(w, h) * 0.02))
    # Fonni xiralashtirishda poyabzal piksellari umuman qatnashmaydi — atrofida «soya/halo» bo'lmaydi
    from scipy import ndimage

    shoe_zone = ndimage.binary_dilation(shoe > 0.05, iterations=max(3, w // 300))
    bg_weight = ((1 - focus) * (~shoe_zone)).astype(np.float32)
    num_mid, den_mid = _lens_blur(linear, bg_weight, radius // 2)
    num_far, den_far = _lens_blur(linear, bg_weight, radius)
    background = (num_mid / np.maximum(den_mid, 1e-3)) * (1 - farness) + (num_far / np.maximum(den_far, 1e-3)) * farness
    background = np.where(den_far > 0.02, background, linear)

    f = focus[..., None]
    sharp = np.asarray(_enhance(img), dtype=np.float32) / 255.0
    out = (sharp ** 2.2) * f + background * (1 - f)
    out = np.clip(out, 0, 1) ** (1 / 2.2)
    return _to_jpeg(Image.fromarray((out * 255).astype(np.uint8)))


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
