@echo off
chcp 65001 >nul
title مُراسِل - جاري التشغيل...

echo.
echo ╔══════════════════════════════════════╗
echo ║         مُراسِل - بدء التشغيل         ║
echo ╚══════════════════════════════════════╝
echo.

:: Check venv exists
if not exist "venv" (
    echo [!] لم يتم الإعداد بعد، شغّل setup.bat أولاً
    pause
    exit /b 1
)

:: Check .env exists
if not exist ".env" (
    echo [!] ملف .env غير موجود، شغّل setup.bat أولاً
    pause
    exit /b 1
)

:: Activate venv
call venv\Scripts\activate.bat

:: Read PORT from .env (default 8000)
set PORT=8000
for /f "tokens=2 delims==" %%a in ('findstr "PORT" .env') do set PORT=%%a

echo [+] جاري تشغيل الخادم على المنفذ %PORT%...
echo [+] سيتم فتح المتصفح تلقائياً خلال ثوانٍ...
echo.
echo [للإيقاف: اضغط Ctrl+C في هذه النافذة]
echo.

:: Open browser after 3 seconds delay (in background)
start /b cmd /c "ping 127.0.0.1 -n 4 >nul && start http://127.0.0.1:%PORT%"

:: Start FastAPI server
python main.py

pause
