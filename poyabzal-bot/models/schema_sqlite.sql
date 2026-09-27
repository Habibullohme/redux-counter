-- SQLite sxemasi. Bot ishga tushganda avtomatik yaratiladi.
-- Supabase (PostgreSQL) uchun tayyor nusxa: models/schema_postgres.sql
-- Pul summalari butun son (so'm) sifatida saqlanadi, vaqt — ISO-8601 matn (UTC).

-- Do'konlar (multi-tenant: keyinchalik boshqa do'konlar ham qo'shiladi)
CREATE TABLE IF NOT EXISTS shops (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    owner_telegram_id INTEGER,
    channel_id        TEXT,
    created_at        TEXT    NOT NULL
);

-- Mahsulotlar (bitta albom = bitta yuk/partiya)
CREATE TABLE IF NOT EXISTS products (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id            INTEGER NOT NULL REFERENCES shops(id),
    brand              TEXT    NOT NULL,
    source             TEXT,                          -- Chorsu / Namangan
    packs_total        INTEGER NOT NULL,              -- kelgan pachka soni
    packs_sold         INTEGER NOT NULL DEFAULT 0,    -- sotilgan (sayt to'ldiradi)
    cost_price         INTEGER,                       -- kelish narxi, 1 pachka (MAXFIY)
    sale_price         INTEGER NOT NULL,              -- sotish narxi, 1 pachka
    currency           TEXT    NOT NULL DEFAULT 'UZS',
    extra_info         TEXT    NOT NULL DEFAULT '',
    raw_caption        TEXT    NOT NULL DEFAULT '',
    description        TEXT    NOT NULL DEFAULT '',   -- kanalga chiqqan matn
    barcode            TEXT UNIQUE,                   -- sayt shtrix-kod beradi
    status             TEXT    NOT NULL DEFAULT 'pending',
    preview_chat_id    INTEGER,
    preview_message_id INTEGER,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL,
    published_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_shop_status ON products(shop_id, status);

-- Mahsulot rasmlari
CREATE TABLE IF NOT EXISTS product_images (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id        INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    original_file_id  TEXT    NOT NULL,   -- siz yuborgan rasm (Telegram file_id)
    processed_file_id TEXT,               -- studiya fonli rasm (Telegram file_id)
    local_path        TEXT,               -- data/images/... dagi fayl
    created_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_product ON product_images(product_id);

-- Kanaldagi xabarlar (yuk tugaganda shular o'chiriladi)
CREATE TABLE IF NOT EXISTS channel_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    chat_id    TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_channel_messages_product ON channel_messages(product_id);
