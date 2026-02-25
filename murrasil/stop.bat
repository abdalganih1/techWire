@echo off
chcp 65001 >nul
title مُراسِل - إيقاف التشغيل

echo [+] جاري إيقاف الخادم...
taskkill /f /im python.exe >nul 2>&1
echo [✓] تم إيقاف مُراسِل
timeout.exe /t 2 /nobreak >nul
