"""Admin yozgan izohni (caption) tahlil qilish.

Misol:
    "Brend: X, Chorsu, 10 pachka, kelish 150000, sotish 180000"

Narxlar 1 pachka uchun deb hisoblanadi. "150 000", "150,000", "150k",
"150 ming", "1.5 mln" ko'rinishlari ham tushuniladi.
"""
from __future__ import annotations

import re

from models.product import ParsedCaption

# Vergul faqat ajratuvchi bo'lsa bo'lamiz ("150,000" dagi vergulni emas)
_SEGMENT_SPLIT = re.compile(r"[\n;|]+|,(?!\d{3}(?!\d))")
_NUMBER = re.compile(
    r"(\d[\d \u00a0.,']*\d|\d)(?:[ \u00a0]*(mln|million|ming|k)(?![a-z]))?", re.IGNORECASE
)

_BRAND = re.compile(r"^\s*(?:brend|brand|marka|firma)\s*[:\-–—=]?\s*(.+)$", re.IGNORECASE)
_PACKS = re.compile(
    r"(\d+)\s*(?:ta\s*)?(?:pachka|pachk|pach|paket|pack|korobka|karobka|quti)"
    r"|(?:pachka|pachk|korobka|karobka|quti)\w*\s*(?:soni)?\s*[:\-–=]?\s*(\d+)",
    re.IGNORECASE,
)
_COST_WORDS = ("kelish", "tannarx", "olish", "olingan", "kirim")
_SALE_WORDS = ("sotish", "sotuv", "sotiladi", "narx", "optom")
_SOURCES = {"chorsu": "Chorsu", "namangan": "Namangan"}
_SOURCE_NOISE = re.compile(r"(?i)\b(?:chorsu|namangan)\w*|\b(?:yuk|keldi|kelgan|manba)\b")


def parse_money(text: str) -> int | None:
    """Matndagi birinchi pul miqdorini so'mda qaytaradi."""
    match = _NUMBER.search(text)
    if not match:
        return None
    raw, suffix = match.group(1), (match.group(2) or "").lower()
    multiplier = {"k": 1_000, "ming": 1_000, "mln": 1_000_000, "million": 1_000_000}.get(suffix, 1)
    compact = raw.replace(" ", "").replace("\u00a0", "").replace("'", "")
    try:
        if multiplier > 1 and re.fullmatch(r"\d+[.,]\d{1,2}", compact):
            value = float(compact.replace(",", ".")) * multiplier
        else:
            value = int(re.sub(r"[.,]", "", compact)) * multiplier
    except ValueError:
        return None
    value = int(round(value))
    return value if value > 0 else None


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in words)


def parse_caption(caption: str | None) -> ParsedCaption:
    result = ParsedCaption(raw=(caption or "").strip())
    if not result.raw:
        return result

    extras: list[str] = []
    for segment in _SEGMENT_SPLIT.split(result.raw):
        segment = segment.strip(" \t.-–—")
        if not segment:
            continue
        lowered = segment.lower()

        source_found = False
        for key, name in _SOURCES.items():
            if key in lowered:
                result.source = result.source or name
                source_found = True

        brand_match = _BRAND.match(segment)
        if brand_match and not result.brand:
            result.brand = brand_match.group(1).strip(" .")
            continue

        # Kelish narxi — hech qachon "extra" ga tushmasligi kerak
        if _contains_any(lowered, _COST_WORDS):
            if result.cost_price is None:
                result.cost_price = parse_money(segment)
            continue

        if _contains_any(lowered, _SALE_WORDS) and not _PACKS.search(segment):
            if result.sale_price is None:
                result.sale_price = parse_money(segment)
            continue

        packs_match = _PACKS.search(segment)
        if packs_match and result.packs is None and "juft" not in lowered:
            result.packs = int(packs_match.group(1) or packs_match.group(2))
            leftover = _PACKS.sub("", segment).strip(" ,:-")
            if leftover:
                extras.append(leftover)
            continue

        if source_found:
            leftover = _SOURCE_NOISE.sub("", segment).strip(" ,:-")
            if leftover and len(leftover) > 2:
                extras.append(leftover)
            continue

        extras.append(segment)

    result.extra = ", ".join(extras)
    return result
