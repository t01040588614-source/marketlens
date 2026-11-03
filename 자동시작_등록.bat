@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MarketLens 자동 시작 등록
echo.
echo  Windows 로그인 후 MarketLens가 자동으로 켜지도록 등록합니다.
echo  - 로그인 약 90초 후 기동 (Docker Desktop 시간 확보)
echo  - AutoStart: .next 유지, 빌드 있으면 npm run start
echo  - 수동 dev: 주식대시보드_통합.bat 메뉴 1 (.next 매번 정리)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-autostart.ps1"
echo.
pause
