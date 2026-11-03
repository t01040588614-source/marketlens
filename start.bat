@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Entry for PowerShell launcher — used by local .bat files
rem Flags: -Dev | -Prod | -Clean | -SkipClean | -AutoStart | -NoBrowser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-servers.ps1" %*
if errorlevel 1 pause
exit /b %errorlevel%
