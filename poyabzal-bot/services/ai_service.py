"""Claude API orqali kanal uchun tavsif yozish.

MUHIM: Claude ga kelish narxi va yuk manbai (Chorsu/Namangan) umuman
yuborilmaydi. Qo'shimcha himoya sifatida tayyor matn tekshiriladi: agar unda
kelish narxi uchrab qolsa, matn tashlab yuboriladi va shablon ishlatiladi.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass

import anthropic

from models.product import ParsedCaption
from services.caption_parser import _NUMBER, parse_money

log = logging.getLogger(__name__)

MAX_CAPTION_LEN = 1000  # Telegram albom izohi chegarasi 1024 belgi

SYSTEM_PROMPT = """Sen ulgurji (optom) poyabzal do'koni uchun Telegram kanalga post yozadigan kopirayterisan.
Do'kon charm, pol-klassika erkaklar oyoq kiyimlarini pachkalab (optom) sotadi. O'quvchilar — boshqa do'kon egalari va ulgurji xaridorlar.

Qoidalar:
- Faqat o'zbek tilida, lotin alifbosida yoz.
- Uzunligi 350-700 belgi. Qisqa, chiroyli, ishonchli ohangda.
- Emoji me'yorida (4-7 ta), har qator boshida bo'lishi mumkin.
- Tuzilishi: 1) e'tiborni tortadigan sarlavha qatori; 2) brend nomi; 3) 1-2 gaplik qisqa tavsif (sifat, charm, klassik uslub);
  4) "💰 Narxi: <narx> so'm (1 pachka)"; 5) "📦 Mavjud: <son> pachka"; 6) qo'shimcha ma'lumot bo'lsa (razmer, rang, pachkadagi juftlar); 7) buyurtma berishga chaqiriq.
- Faqat senga berilgan narx va sonlarni ishlat. Boshqa hech qanday raqam, chegirma, foyda yoki tannarx o'ylab topma.
- Narxni bo'shliq bilan guruhlab yoz: 180 000.
- Markdown yoki HTML belgilarini (*, _, #, <b>) ishlatma — oddiy matn.
- Faqat post matnini qaytar, izoh yoki kirish so'zisiz."""


@dataclass
class DescriptionResult:
    text: str
    from_ai: bool
    note: str = ""


def format_money(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ")


def template_description(parsed: ParsedCaption) -> str:
    """AI ishlamasa ishlatiladigan zaxira shablon."""
    lines = [
        "🔥 Yangi kolleksiya keldi!",
        "",
        f"👞 Brend: {parsed.brand}",
        "Sifatli charm, klassik uslub — mijozlaringiz albatta yoqtiradi.",
        "",
        f"💰 Narxi: {format_money(parsed.sale_price)} so'm (1 pachka)",
        f"📦 Mavjud: {parsed.packs} pachka",
    ]
    if parsed.extra:
        lines.append(f"ℹ️ {parsed.extra}")
    lines += ["", "📩 Buyurtma uchun yozing!"]
    return "\n".join(lines)


def leaks_cost(text: str, cost_price: int | None) -> bool:
    """Matnda kelish narxi (istalgan ko'rinishda) bormi?"""
    if not cost_price:
        return False
    for match in _NUMBER.finditer(text):
        if parse_money(match.group(0)) == cost_price:
            return True
    return False


def mentions_price(text: str, sale_price: int | None) -> bool:
    if not sale_price:
        return True
    return any(parse_money(m.group(0)) == sale_price for m in _NUMBER.finditer(text))


class AIService:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90.0, max_retries=2)
        self.model = model

    def _build_user_prompt(self, parsed: ParsedCaption) -> str:
        # Faqat xaridorga ko'rsatsa bo'ladigan ma'lumotlar — kelish narxi va manba YO'Q
        parts = [
            f"Brend: {parsed.brand}",
            f"Narxi (1 pachka): {format_money(parsed.sale_price)} so'm",
            f"Mavjud: {parsed.packs} pachka",
        ]
        if parsed.extra:
            parts.append(f"Qo'shimcha: {parsed.extra}")
        return "Quyidagi mahsulot uchun kanal posti yoz:\n" + "\n".join(parts)

    async def generate_description(self, parsed: ParsedCaption) -> DescriptionResult:
        fallback = template_description(parsed)
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": self._build_user_prompt(parsed)}],
            )
        except anthropic.AuthenticationError:
            log.error("ANTHROPIC_API_KEY noto'g'ri")
            return DescriptionResult(fallback, False, "Claude API kaliti noto'g'ri — shablon ishlatildi.")
        except anthropic.RateLimitError:
            log.warning("Claude API limitga yetdi")
            return DescriptionResult(fallback, False, "Claude API band (limit) — shablon ishlatildi.")
        except anthropic.APIStatusError as exc:
            log.error("Claude API xatosi %s: %s", exc.status_code, exc.message)
            return DescriptionResult(fallback, False, f"Claude API xatosi ({exc.status_code}) — shablon ishlatildi.")
        except anthropic.APIConnectionError:
            log.exception("Claude API ga ulanib bo'lmadi")
            return DescriptionResult(fallback, False, "Claude API ga ulanib bo'lmadi — shablon ishlatildi.")

        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("Claude javobi to'liq emas: %s", response.stop_reason)
            return DescriptionResult(fallback, False, "AI javobi to'liq kelmadi — shablon ishlatildi.")

        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        text = text.replace("**", "").replace("__", "")

        if not text:
            return DescriptionResult(fallback, False, "AI bo'sh javob qaytardi — shablon ishlatildi.")
        if leaks_cost(text, parsed.cost_price):
            log.warning("AI matnida kelish narxi topildi — matn rad etildi")
            return DescriptionResult(fallback, False, "AI matnida kelish narxi chiqib qoldi — shablon ishlatildi.")
        if not mentions_price(text, parsed.sale_price):
            return DescriptionResult(fallback, False, "AI narxni noto'g'ri yozdi — shablon ishlatildi.")
        if len(text) > MAX_CAPTION_LEN - 150:
            return DescriptionResult(fallback, False, "AI matni juda uzun chiqdi — shablon ishlatildi.")
        return DescriptionResult(text, True)


def build_channel_caption(description: str, contact: str) -> str:
    """Kanal uchun yakuniy izoh (HTML xavfsiz)."""
    text = description.strip()
    if contact:
        text += f"\n\n📞 {contact}"
    # Chegara escape dan oldin qirqiladi, aks holda "&amp;" kabi belgi yarmida kesilishi mumkin
    return html.escape(text[:MAX_CAPTION_LEN], quote=False)
