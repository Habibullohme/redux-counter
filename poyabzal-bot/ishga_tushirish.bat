@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Poyabzal bot

where python >nul 2>nul
if errorlevel 1 goto no_python

if exist ".venv\Scripts\python.exe" goto install
echo Birinchi ishga tushirish: kerakli dasturlar o'rnatilmoqda. 5-10 daqiqa kuting...
python -m venv .venv
if errorlevel 1 goto venv_error

:install
echo Kutubxonalar tekshirilmoqda...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto pip_error

if exist ".env" goto run
copy ".env.example" ".env" >nul
echo.
echo ============================================================
echo  Hozir Bloknot ochiladi. Unga quyidagilarni yozing:
echo    BOT_TOKEN, CHANNEL_ID, ADMIN_ID, GEMINI_API_KEY
echo  Keyin Ctrl+S bilan saqlang va Bloknotni yoping.
echo ============================================================
notepad ".env"

:run
echo.
echo Bot ishga tushmoqda. To'xtatish uchun shu oynani yoping.
echo.
".venv\Scripts\python.exe" main.py
echo.
echo Bot to'xtadi. Xato bo'lsa, yuqoridagi yozuvni o'qing yoki data\bot.log faylini yuboring.
pause
exit /b 0

:no_python
echo [XATO] Python topilmadi.
echo https://www.python.org/downloads/ dan Python 3.12 ni o'rnating.
echo O'rnatishda "Add Python to PATH" belgisini albatta qo'ying, keyin shu faylni qayta oching.
pause
exit /b 1

:venv_error
echo [XATO] Virtual muhit yaratib bo'lmadi. Python ni qayta o'rnatib ko'ring.
pause
exit /b 1

:pip_error
echo [XATO] Kutubxonalarni o'rnatib bo'lmadi. Internetni tekshirib, qayta urinib ko'ring.
pause
exit /b 1
