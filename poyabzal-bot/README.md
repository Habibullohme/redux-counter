# 👞 Poyabzal Optom — Telegram bot

Ulgurji (optom) poyabzal do'koni uchun bot. Siz rasm va ma'lumot yuborasiz, bot:

1. Har bir rasm fonini olib tashlaydi va chiroyli **studiya foni** qo'yadi (och gradient, yumshoq soya, mahsulot markazda).
2. **AI** (Google Gemini — bepul limit bilan, yoki Claude) yordamida o'zbek tilida xaridorlar uchun qisqa tavsif yozadi.
   AI kaliti bo'lmasa ham bot ishlaydi — tavsif tayyor shablon bo'yicha yoziladi.
3. Sizga **ko'rinishini** yuboradi, ostida ikkita tugma: **✅ Tasdiqlash** va **❌ Bekor qilish**.
4. Tasdiqlasangiz, kanalga **albom** qilib joylaydi.
5. Hammasini (kelish narxi ham) bazaga saqlaydi.

> 🔒 **Kelish narxi kanalga hech qachon chiqmaydi.** U AI ga umuman yuborilmaydi, tayyor matn esa
> qo'shimcha tekshiriladi. Yuk manbai (Chorsu/Namangan) ham kanalga chiqmaydi.
> Bu ikkalasini faqat siz ko'rasiz.

---

## 📋 Mundarija

1. [Nima kerak bo'ladi](#1-nima-kerak-boladi)
2. [Bot yaratish (BOT_TOKEN)](#2-bot-yaratish-bot_token)
3. [ADMIN_ID ni olish](#3-admin_id-ni-olish)
4. [Kanal tayyorlash va CHANNEL_ID ni olish](#4-kanal-tayyorlash-va-channel_id-ni-olish)
5. [AI kaliti (GEMINI_API_KEY) — ixtiyoriy](#5-ai-kaliti-gemini_api_key--ixtiyoriy)
6. [O'rnatish](#6-ornatish)
7. [.env faylini to'ldirish](#7-env-faylini-toldirish)
8. [Ishga tushirish](#8-ishga-tushirish)
9. [Botni sinab ko'rish](#9-botni-sinab-korish)
10. [Kundalik foydalanish](#10-kundalik-foydalanish)
11. [Muammolar va yechimlar](#11-muammolar-va-yechimlar)
12. [Loyiha tuzilishi (dasturchi uchun)](#12-loyiha-tuzilishi-dasturchi-uchun)

---

## 1. Nima kerak bo'ladi

- Kompyuter yoki server (Windows, macOS yoki Linux). Bot ishlashi uchun u **yoqilgan** turishi kerak.
- **Python 3.12** (3.10–3.12 ishlaydi, eng ishonchlisi 3.12). Tekshirish uchun terminalda yozing:
  ```bash
  python --version
  ```
  Agar yo'q bo'lsa: <https://www.python.org/downloads/> dan yuklab o'rnating.
  **Windows da** o'rnatishda **"Add Python to PATH"** belgisini albatta qo'ying.
- Internet (birinchi ishga tushishda ~180 MB rasm modeli yuklab olinadi).
- Kamida **2 GB** operativ xotira (RAM).

> 💡 **Terminal nima?** Windows da: `Win` tugmasi → `cmd` yoki `PowerShell` deb yozing.
> macOS da: `Terminal` dasturi. Quyidagi buyruqlarni o'sha yerga yozib `Enter` bosasiz.

---

## 2. Bot yaratish (BOT_TOKEN)

1. Telegramda **[@BotFather](https://t.me/BotFather)** ni oching.
2. `/newbot` yuboring.
3. Botga nom bering (masalan: `Poyabzal Optom Bot`).
4. Username bering, oxiri `bot` bilan tugashi shart (masalan: `poyabzal_optom_bot`).
5. BotFather sizga shunga o'xshash **token** beradi:
   ```
   7123456789:AAHk3j...uzun-matn
   ```
   Shuni saqlab qo'ying — bu **BOT_TOKEN**. Uni hech kimga bermang!

---

## 3. ADMIN_ID ni olish

ADMIN_ID — bu **sizning** Telegram raqamli ID ingiz. Botdan faqat shu ID egasi foydalana oladi.

1. Telegramda **[@userinfobot](https://t.me/userinfobot)** ni oching.
2. `/start` bosing.
3. U sizga `Id: 123456789` ko'rinishida raqam yuboradi. Shu raqam — **ADMIN_ID**.

---

## 4. Kanal tayyorlash va CHANNEL_ID ni olish

### 4.1. Botni kanalga admin qilish (MAJBURIY)

1. Kanalingizni oching → kanal nomiga bosing → **Administratorlar** (Administrators).
2. **Administrator qo'shish** → botingiz username ini qidiring (masalan `@poyabzal_optom_bot`).
3. Quyidagi huquqlarni yoqing:
   - ✅ **Xabar joylash** (Post messages)
   - ✅ **Boshqalarning xabarlarini o'chirish** (Delete messages) — yuk tugaganda o'chirish uchun
   - ✅ **Xabarlarni tahrirlash** (Edit messages)
4. Saqlang.

### 4.2. CHANNEL_ID ni bilish

**A usul — ochiq kanal bo'lsa (eng oson):**
Kanal havolasi `t.me/poyabzal_optom` bo'lsa, CHANNEL_ID sifatida shunchaki yozasiz:
```
CHANNEL_ID=@poyabzal_optom
```

**B usul — yopiq (shaxsiy) kanal bo'lsa:**
1. Kanalingizdan istalgan bitta xabarni **[@userinfobot](https://t.me/userinfobot)** ga **forward** (uzatish) qiling.
   (Agar u javob bermasa, **[@getidsbot](https://t.me/getidsbot)** yoki **[@RawDataBot](https://t.me/RawDataBot)** ni sinab ko'ring.)
2. Javobda `-100` bilan boshlanuvchi raqam chiqadi, masalan `-1001987654321`.
3. Shu raqam — **CHANNEL_ID** (minus belgisi bilan birga yozing!):
   ```
   CHANNEL_ID=-1001987654321
   ```

---

## 5. AI kaliti (GEMINI_API_KEY) — ixtiyoriy

Tavsifni AI yozishi uchun kalit kerak. **Kalitsiz ham bot to'liq ishlaydi** — faqat tavsif
har safar bir xil tayyor shablon bo'yicha yoziladi. Avval kalitsiz sinab ko'rsangiz ham bo'ladi.

### Google Gemini (tavsiya — bepul limiti bor)

1. <https://aistudio.google.com/apikey> ga Google akkauntingiz (Gmail) bilan kiring.
2. **Create API key** (API kalit yaratish) tugmasini bosing.
3. Hosil bo'lgan `AIza...` bilan boshlanuvchi kalitni nusxalang — bu **GEMINI_API_KEY**.

Bilishingiz kerak:
- Bepul rejada kunlik/daqiqalik **limit** bor. Limit tugasa bot to'xtamaydi — o'sha postni shablon bilan yozadi, keyin limit o'zi tiklanadi.
- Bepul rejada Google yuborilgan matnlardan o'z xizmatlarini yaxshilash uchun foydalanishi mumkin. Botdan AI ga faqat brend, sotish narxi, pachka soni va qo'shimcha ma'lumot boradi — **kelish narxi va manba hech qachon yuborilmaydi**.
- Limit va shartlar vaqti-vaqti bilan o'zgaradi — aniq ma'lumot AI Studio saytida.
- Agar "model topilmadi" degan ogohlantirish chiqsa, `.env` dagi `GEMINI_MODEL` ni AI Studio da ko'rsatilgan boshqa modelga (masalan `gemini-2.5-flash`) almashtiring.

### Claude (ixtiyoriy, pullik)

O'zbekcha matn sifati yuqoriroq, har bir tavsif taxminan 1 sent turadi.
<https://console.anthropic.com> da hisobni to'ldirib, **API Keys** dan `sk-ant-...` kalit oling va `.env` da:
```env
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 6. O'rnatish

### ⚡ Eng oson yo'l (Windows)

1. Loyihani yuklab oling: GitHub sahifasida yashil **Code** tugmasi → **Download ZIP** → arxivni oching.
2. `poyabzal-bot` papkasiga kiring.
3. **`ishga_tushirish.bat`** faylini sichqoncha bilan **ikki marta bosing**.
   - Birinchi safar kerakli dasturlar o'zi o'rnatiladi (5–10 daqiqa).
   - Keyin Bloknot ochiladi — unga tokenlarni yozasiz (7-bo'lim), **Ctrl+S** bosib saqlaysiz va yopasiz.
   - Bot ishga tushadi. Qora oyna ochiq turgan paytda bot ishlaydi, yopsangiz to'xtaydi.
4. Keyingi safarlar: faqat `ishga_tushirish.bat` ni ikki marta bosasiz.

macOS / Linux: terminalda `bash ishga_tushirish.sh`.

> Windows "Noma'lum dastur" deb ogohlantirsa: **Batafsil** (More info) → **Baribir ishga tushirish** (Run anyway).

Quyidagi qo'lda o'rnatish — agar oson yo'l ishlamasa.

### Qo'lda o'rnatish

Terminalni oching va quyidagilarni **ketma-ket** bajaring.

**1) Loyiha papkasiga o'ting** (yo'lni o'zingiznikiga moslang):
```bash
cd poyabzal-bot
```

**2) Virtual muhit yarating** (kutubxonalar tartibli turishi uchun, bir marta qilinadi):

Windows:
```bash
python -m venv .venv
.venv\Scripts\activate
```
macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Muvaffaqiyatli bo'lsa, terminal satri boshida `(.venv)` yozuvi paydo bo'ladi.

**3) Kutubxonalarni o'rnating** (bir necha daqiqa olishi mumkin):
```bash
pip install -r requirements.txt
```

---

## 7. .env faylini to'ldirish

Maxfiy ma'lumotlar kodda emas, `.env` degan faylda saqlanadi.

1. `.env.example` faylidan nusxa olib, nomini `.env` qiling:
   - Windows: `copy .env.example .env`
   - macOS/Linux: `cp .env.example .env`
2. `.env` ni istalgan matn muharririda (Notepad, VS Code) oching va to'ldiring:

```env
BOT_TOKEN=7123456789:AAHk3j...
CHANNEL_ID=-1001987654321
ADMIN_ID=123456789

AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...

SHOP_NAME=Poyabzal Optom
CONTACT=+998 90 123 45 67
```

- `BOT_TOKEN` — 2-bo'limdan, `ADMIN_ID` — 3-bo'limdan, `CHANNEL_ID` — 4-bo'limdan (yoki `@kanal_username`).
- `GEMINI_API_KEY` — 5-bo'limdan. **Bo'sh qoldirsangiz ham bo'ladi** — unda tavsif shablon bo'yicha yoziladi.

> ⚠️ `=` belgisi atrofida bo'sh joy qoldirmang. Qo'shtirnoq kerak emas.
> ⚠️ `.env` faylini hech kimga yubormang va internetga joylamang.

`CONTACT` — kanal postining oxirida chiqadigan bog'lanish ma'lumoti (ixtiyoriy).

---

## 8. Ishga tushirish

Virtual muhit yoqilgan holda (`(.venv)` ko'rinib turibdi):
```bash
python main.py
```

Birinchi marta rasm modeli (~180 MB) yuklab olinadi. Keyin shunday yozuvlarni ko'rasiz:
```
Bot ishga tushdi: @poyabzal_optom_bot
Tayyor! Botga rasm yuborishingiz mumkin.
```

- To'xtatish: terminalda `Ctrl + C`.
- Terminalni yopsangiz bot ham to'xtaydi. Keyingi safar ishga tushirish uchun:
  ```bash
  cd poyabzal-bot
  .venv\Scripts\activate        # Windows
  source .venv/bin/activate     # macOS/Linux
  python main.py
  ```

---

## 9. Botni sinab ko'rish

Bot ishlab turgan paytda quyidagi qadamlarni bajaring:

**✅ 1-sinov: bot javob beryaptimi?**
Botingizga `/start` yuboring → yordam matni kelishi kerak.

**✅ 2-sinov: bitta rasm**
1. Poyabzal rasmini yuboring.
2. Rasm **izohiga** (caption — rasm tagidagi "Izoh qo'shish" joyi) yozing:
   ```
   Brend: Test, Chorsu, 10 pachka, kelish 150000, sotish 180000
   ```
3. Bot "⏳ qayta ishlanmoqda..." deydi (bitta rasm ~5–15 soniya).
4. Sizga **studiya fonli rasm + tavsif** keladi, ostida alohida xabarda:
   - kelish narxi, sotish narxi, **foyda** (faqat siz ko'rasiz),
   - **✅ Tasdiqlash** va **❌ Bekor qilish** tugmalari.
5. Tavsifda **150 000 (kelish narxi) YO'Qligini** tekshiring.

**✅ 3-sinov: albom**
Galereyadan 2–5 ta rasmni **birga** tanlab yuboring (albom), izohni birinchisiga yozing.
Hammasi bitta albom bo'lib qaytishi kerak.

**✅ 4-sinov: kanalga joylash**
**✅ Tasdiqlash** ni bosing → kanalingizni oching → albom tavsif bilan chiqqan bo'lishi kerak.
Bot xabari "✅ Kanalga joylandi! (#1)" ga o'zgaradi.

**✅ 5-sinov: bekor qilish**
Yana bitta rasm yuboring va **❌ Bekor qilish** ni bosing → kanalga hech narsa chiqmasligi kerak.

**✅ 6-sinov: ro'yxat va o'chirish**
- `/mahsulotlar` → barcha mahsulotlar va holati.
- `/tugadi 1` → 1-mahsulot kanaldan o'chadi va "tugagan" deb belgilanadi.

**✅ 7-sinov: begona odam**
Do'stingizdan botga yozib ko'rishini so'rang → unga "⛔ Bu bot faqat do'kon egasi uchun" chiqishi kerak.

**✅ 8-sinov: xato izoh**
Rasmni izohsiz yuboring → bot nima yetishmayotganini aytadi.

---

## 10. Kundalik foydalanish

**Izoh yozish qoidalari** (tartib muhim emas, vergul yoki yangi qator bilan ajrating):

| Nima | Qanday yozish | Majburiy? |
|---|---|---|
| Brend | `Brend: Baldinini` | ✅ ha |
| Pachka soni | `10 pachka` yoki `pachka: 10` | ✅ ha |
| Sotish narxi (1 pachka) | `sotish 180000` | ✅ ha |
| Kelish narxi (1 pachka) | `kelish 150000` | foyda hisobi uchun kerak |
| Manba | `Chorsu` yoki `Namangan` | ixtiyoriy |
| Qo'shimcha | `razmer 39-44, qora, pachkada 6 juft` | ixtiyoriy (kanalga chiqadi) |

Narxni istalgan ko'rinishda yozish mumkin: `180000`, `180 000`, `180,000`, `180k`, `180 ming`.

**Misollar:**
```
Brend: Baldinini, Chorsu, 10 pachka, kelish 150000, sotish 180000
```
```
Brend: Ecco
Namangan
15 pachka
kelish 150 ming
sotish 185 ming
razmer 39-44, qora rang, pachkada 6 juft
```

**Buyruqlar:**
- `/mahsulotlar` — oxirgi 10 ta mahsulot va raqamlari
- `/tugadi 12` — 12-raqamli yuk tugadi → kanaldan o'chiriladi
- `/yordam` — yordam

---

## 11. Muammolar va yechimlar

| Muammo | Yechim |
|---|---|
| `[XATO] BOT_TOKEN .env faylida to'ldirilmagan` | `.env` fayli `main.py` bilan bitta papkada ekanini va to'ldirilganini tekshiring. Fayl nomi aynan `.env` bo'lsin (`.env.txt` emas). |
| Bot javob bermayapti | Terminalda bot ishlab turganini tekshiring. `ADMIN_ID` to'g'rimi? |
| "Kanalga joylab bo'lmadi" | Bot kanalda **admin**mi va "Xabar joylash" huquqi bormi? `CHANNEL_ID` `-100` bilan boshlanadimi? |
| "shablon ishlatildi" degan ogohlantirish | Ogohlantirishda sababi yozilgan: kalit noto'g'ri (`GEMINI_API_KEY` ni tekshiring), bepul limit tugagan (biroz kuting) yoki model topilmadi (`GEMINI_MODEL` ni o'zgartiring). |
| "AI kaliti yo'q" | `.env` da `GEMINI_API_KEY` bo'sh. Bu xato emas — shablon ishlaydi. AI kerak bo'lsa, 5-bo'limga qarang. |
| "fonni olib bo'lmadi" | Rasm juda qorong'i yoki mahsulot fon bilan bir xil rangda. Yorug'roq, oddiy fonda suratga oling. |
| `/tugadi` xabarni o'chira olmadi | Botga "Xabarlarni o'chirish" huquqini bering. Telegram juda eski xabarlarni o'chirishga ruxsat bermasligi mumkin — ularni qo'lda o'chiring. |
| `pip` topilmadi | Windows da Python ni qayta o'rnating va **"Add Python to PATH"** ni belgilang. |

Barcha xatolar `data/bot.log` fayliga ham yoziladi — muammo bo'lsa shu faylni dasturchiga yuboring
(unda maxfiy kalitlar yo'q).

---

## 12. Loyiha tuzilishi (dasturchi uchun)

```
poyabzal-bot/
├── main.py                 # ishga tushirish, dispatcher, xatolarni ushlash
├── config.py               # .env ni o'qish va tekshirish
├── requirements.txt
├── .env.example            # .env namunasi (maxfiy ma'lumotsiz)
├── bot/
│   ├── filters.py          # IsAdmin — faqat ADMIN_ID
│   ├── keyboards.py        # Tasdiqlash / Bekor qilish tugmalari
│   ├── middlewares.py      # albom (media group) ni yig'ish
│   └── handlers/
│       ├── products.py     # rasm → ishlov → ko'rinish → kanal
│       └── common.py       # /start, /mahsulotlar, /tugadi, begonalar
├── services/
│   ├── caption_parser.py   # izohdan brend/pachka/narxlarni ajratish
│   ├── image_service.py    # rembg + studiya fon
│   ├── ai_service.py       # Gemini / Claude / shablon, kelish narxi sizib chiqishidan himoya
│   ├── channel_service.py  # kanalga joylash / o'chirish (sayt integratsiyasi uchun)
│   └── database.py         # SQLite repository
├── models/
│   ├── product.py          # dataclass modellari va holatlar
│   ├── schema_sqlite.sql   # joriy baza sxemasi
│   └── schema_postgres.sql # Supabase uchun xuddi shu sxema
└── data/                   # (git ga kirmaydi) shop.db, images/, bot.log
```

**Baza jadvallari:** `shops` → `products` → `product_images`, `channel_messages`.

**Kelajakdagi reja bilan bog'liqlik:**
- **Multi-tenant:** har bir mahsulot `shop_id` ga bog'langan. Hozir bitta do'kon (`ADMIN_ID` egasi) avtomatik yaratiladi.
- **Web sayt:** `products.packs_sold`, `products.barcode` ustunlari tayyor. Rasmlar `data/images/<id>/` da saqlanadi.
- **Avtomatik o'chirish:** sayt yuk tugaganini aniqlaganda `services/channel_service.remove_product_posts()` ni chaqiradi — `/tugadi` buyrug'i ham aynan shuni ishlatadi.
- **Supabase ga ko'chish:** `models/schema_postgres.sql` ni Supabase SQL Editor da ishga tushiring, ustun nomlari bir xil — ma'lumotni CSV orqali ko'chirish mumkin. Kodda faqat `services/database.py` almashtiriladi.
- Pul summalari butun son (so'm), vaqt — UTC ISO-8601 formatida.
