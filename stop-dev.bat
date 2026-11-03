@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MarketLens Stop (Local)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev-ports.ps1"
set "EC=%ERRORLEVEL%"
echo.
if not "%EC%"=="0" (
    echo  일부 포트가 남아 있습니다. Docker/API 창을 확인하세요.
) else (
    echo  Broken UI? 통합.bat 메뉴 1 ^(.next 정리^)
)
echo.
pause
exit /b %EC%
