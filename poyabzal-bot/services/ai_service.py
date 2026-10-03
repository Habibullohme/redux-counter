"""AI (Gemini yoki Claude) orqali kanal uchun tavsif yozish.

AI tanlash .env dagi AI_PROVIDER orqali: none (faqat shablon, standart), gemini yoki claude.
Kalit bo'lmasa yoki AI ishlamasa, tavsif tayyor shablon bo'yicha yoziladi.

MUHIM: AI ga kelish narxi va yuk manbai (Chorsu/Namangan) umuman
yuborilmaydi. Qo'shimcha himoya sifatida tayyor matn tekshiriladi: agar unda
kelish narxi uchrab qolsa, matn tashlab yuboriladi va shablon ishlatiladi.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass

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


class AIProviderError(Exception):
    """AI xizmatidan foydalanib bo'lmadi. `note` — adminga ko'rsatiladigan qisqa sabab."""

    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


class GeminiProvider:
    """Google Gemini (bepul limiti bor). Kalit: https://aistudio.google.com/apikey"""

    name = "Gemini"

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90_000))
        self.model = model

    async def write(self, system: str, prompt: str) -> str:
        from google.genai import errors

        types = self._types
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.8,
                    max_output_tokens=4096,
                ),
            )
        except errors.ClientError as exc:
            log.error("Gemini xatosi %s: %s", exc.code, exc.message)
            if exc.code == 429:
                raise AIProviderError("Gemini bepul limiti tugadi (keyinroq qayta tiklanadi)") from exc
            if exc.code == 404:
                raise AIProviderError(f"Gemini modeli topilmadi: {self.model} (.env dagi GEMINI_MODEL ni tekshiring)") from exc
            if exc.code in (400, 401, 403):
                raise AIProviderError("Gemini kaliti noto'g'ri yoki bu mintaqada ruxsat yo'q") from exc
            raise AIProviderError(f"Gemini xatosi ({exc.code})") from exc
        except errors.APIError as exc:
            log.error("Gemini server xatosi %s: %s", exc.code, exc.message)
            raise AIProviderError(f"Gemini server xatosi ({exc.code})") from exc

        candidate = response.candidates[0] if response.candidates else None
        finish = getattr(getattr(candidate, "finish_reason", None), "name", "STOP")
        if candidate is None or finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            log.warning("Gemini javobi to'liq emas: %s", finish if candidate else response.prompt_feedback)
            raise AIProviderError("AI javobi to'liq kelmadi")
        return response.text or ""


class ClaudeProvider:
    """Anthropic Claude (pullik, console.anthropic.com)."""

    name = "Claude"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90.0, max_retries=2)
        self.model = model

    async def write(self, system: str, prompt: str) -> str:
        anthropic = self._anthropic
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise AIProviderError("Claude API kaliti noto'g'ri") from exc
        except anthropic.RateLimitError as exc:
            raise AIProviderError("Claude API band (limit)") from exc
        except anthropic.APIStatusError as exc:
            log.error("Claude API xatosi %s: %s", exc.status_code, exc.message)
            raise AIProviderError(f"Claude API xatosi ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError("Claude API ga ulanib bo'lmadi") from exc

        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("Claude javobi to'liq emas: %s", response.stop_reason)
            raise AIProviderError("AI javobi to'liq kelmadi")
        return "\n".join(b.text for b in response.content if b.type == "text")


def build_provider(provider: str, gemini_key: str, gemini_model: str, claude_key: str, claude_model: str):
    """.env dagi AI_PROVIDER bo'yicha AI tanlaydi. Kalit bo'lmasa — None (shablon rejimi)."""
    if provider == "gemini" and gemini_key:
        return GeminiProvider(gemini_key, gemini_model)
    if provider == "claude" and claude_key:
        return ClaudeProvider(claude_key, claude_model)
    return None


class AIService:
    def __init__(self, provider: GeminiProvider | ClaudeProvider | None, template_only: bool = False) -> None:
        self.provider = provider
        # template_only=True — AI ataylab o'chirilgan (AI_PROVIDER=none), ogohlantirish kerak emas
        self.template_only = template_only

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
        if self.provider is None:
            note = "" if self.template_only else "AI kaliti yo'q — tavsif shablon bo'yicha yozildi."
            return DescriptionResult(fallback, False, note)

        try:
            text = await self.provider.write(SYSTEM_PROMPT, self._build_user_prompt(parsed))
        except AIProviderError as exc:
            return DescriptionResult(fallback, False, f"{exc.note} — shablon ishlatildi.")
        except Exception:  # noqa: BLE001 — tarmoq va boshqa kutilmagan xatolar: bot to'xtamasin
            log.exception("%s ga murojaatda xato", self.provider.name)
            return DescriptionResult(fallback, False, f"{self.provider.name} ga ulanib bo'lmadi — shablon ishlatildi.")

        text = text.strip().replace("**", "").replace("__", "")
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
