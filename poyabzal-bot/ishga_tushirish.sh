#!/usr/bin/env bash
# macOS / Linux uchun: terminalda  bash ishga_tushirish.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[XATO] Python topilmadi. https://www.python.org/downloads/ dan Python 3.12 ni o'rnating."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Birinchi ishga tushirish: kerakli dasturlar o'rnatilmoqda. 5-10 daqiqa kuting..."
  python3 -m venv .venv
fi

echo "Kutubxonalar tekshirilmoqda..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo
  echo "=== .env fayli yaratildi. Uni oching va BOT_TOKEN, CHANNEL_ID, ADMIN_ID, GEMINI_API_KEY ni yozing ==="
  echo "=== Keyin shu buyruqni qayta ishga tushiring: bash ishga_tushirish.sh ==="
  exit 0
fi

echo "Bot ishga tushmoqda. To'xtatish: Ctrl+C"
exec .venv/bin/python main.py
