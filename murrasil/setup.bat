@echo off
chcp 65001 >nul
title مُراسِل - الإعداد الأول

echo.
echo ╔══════════════════════════════════════╗
echo ║        مُراسِل - إعداد المشروع        ║
echo ╚══════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] خطأ: Python غير مثبت على جهازك
    echo [!] حمّله من: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [✓] Python موجود

:: Create virtual environment
if not exist "venv" (
    echo [+] جاري إنشاء البيئة الافتراضية...
    python -m venv venv
    echo [✓] تم إنشاء البيئة الافتراضية
) else (
    echo [✓] البيئة الافتراضية موجودة مسبقاً
)

:: Activate and install dependencies
echo [+] جاري تثبيت المكتبات...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
echo [✓] تم تثبيت جميع المكتبات

:: Create .env from .env.example if not exists
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║  [!] تم إنشاء ملف .env                              ║
    echo ║  [!] افتحه والصق مفتاح Gemini API في السطر الأول   ║
    echo ║  [!] احصل على المفتاح من:                           ║
    echo ║      https://aistudio.google.com/app/apikey          ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    pause
    start notepad .env
) else (
    echo [✓] ملف .env موجود مسبقاً
)

echo.
echo [✓] اكتمل الإعداد! الآن شغّل start.bat
echo.
pause
