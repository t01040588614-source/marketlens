@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title MarketLens - 통합 (실행 / Docker / E2E / 모바일 QA)

rem 더블클릭: 메뉴 1과 동일 — API+Next dev, warmup, verify, WS 실시간 경로
if /i "%~1"=="menu" goto MENU
if /i "%~1"=="m" goto MENU
if not "%~1"=="" goto DISPATCH_ARG
goto RUN_DEV

:DISPATCH_ARG
if /i "%~1"=="1" (shift & goto RUN_DEV)
if /i "%~1"=="2" (shift & goto RUN_PROD)
if /i "%~1"=="3" (shift & goto RUN_DOCKER)
if /i "%~1"=="4" (shift & goto RUN_DOCKER_DOWN)
if /i "%~1"=="5" (shift & goto RUN_STOP_DEV)
if /i "%~1"=="6" (shift & goto E2E_ALL)
if /i "%~1"=="7" (shift & goto E2E_STICKY)
if /i "%~1"=="8" (shift & goto E2E_MOBILE)
if /i "%~1"=="9" (shift & goto E2E_UI_BUNDLE)
echo Unknown option: %~1
pause
exit /b 1

:MENU
cls
echo.
echo  ============================================================
echo   MarketLens 통합 런처
echo  ============================================================
echo.
echo   [스택 실행]  (더블클릭 = 1, 전역 WS+LiveStockQuerySync)
echo     1  로컬 개발     start.bat -Dev  (API:8000 + Next dev)
echo     2  로컬 프로덕션 start.bat -Prod (build + start)
echo     3  Docker 전체   docker-compose-up.ps1 -Build
echo     4  Docker 중지   docker-compose-up.ps1 -Down
echo     5  개발 서버 중지 stop-dev.bat  (8000 API + 3000/3001 Next)
echo.
echo   [UI / CSS]
echo     - Next dev 포트 3000 고정 ^(3001 구버전 UI 방지^)
echo     - 깨짐 시: 메뉴 5 후 메뉴 1 ^(.next 정리^) / Ctrl+Shift+R
echo     - 티커 sticky, 표 헤더 고정 CSS 반영
echo     - 수동: my-frontend\e2e\MOBILE_VIEWPORT_CHECKLIST.md
echo.
echo   [Playwright]
echo     6  E2E 전체   7  sticky 2건   8  모바일 캡처   9  UI QA (7+8)
echo     - 3000/3001 정리 + PLAYWRIGHT_REUSE_SERVER=0 + npm run dev
echo     - API :8000 권장 ^(메뉴 1 또는 3^) — E2E는 API 끄지 않음
echo.
echo     0  종료   ^|  http://127.0.0.1:3000/markets
echo.
set "PICK="
set /p PICK="번호 입력 (0-9): "
if "%PICK%"=="0" exit /b 0
if "%PICK%"=="1" goto RUN_DEV
if "%PICK%"=="2" goto RUN_PROD
if "%PICK%"=="3" goto RUN_DOCKER
if "%PICK%"=="4" goto RUN_DOCKER_DOWN
if "%PICK%"=="5" goto RUN_STOP_DEV
if "%PICK%"=="6" goto E2E_ALL
if "%PICK%"=="7" goto E2E_STICKY
if "%PICK%"=="8" goto E2E_MOBILE
if "%PICK%"=="9" goto E2E_UI_BUNDLE
echo.
echo  잘못된 입력입니다.
timeout /t 2 /nobreak >nul
goto MENU

:RUN_DEV
echo.
echo  [1] Local dev — FastAPI :8000 + Next :3000 + quote warmup + verify-stack/realtime
echo  Optional: start.bat -Dev -SkipClean -NoBrowser  ^|  메뉴: 통합.bat menu
echo.
call "%~dp0start.bat" -Dev %*
if errorlevel 1 (
    echo.
    echo  [FAILED] Docker Desktop / stop-dev.bat / 메뉴 4 Docker 중지 후 재시도
    pause
    goto MENU
)
echo.
echo  Done. stop-dev.bat 또는 메뉴 5
pause
goto MENU

:RUN_PROD
echo.
echo  [2] Production local — npm run build + start
echo.
call "%~dp0start.bat" -Prod %*
if errorlevel 1 (
    echo  [FAILED] Stock Frontend 창의 빌드 로그 확인
    pause
    goto MENU
)
timeout /t 3 /nobreak >nul
goto MENU

:RUN_DOCKER
echo.
echo  [3] Docker full stack — Postgres + API + Next containers
echo  Optional: -NoBrowser
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\docker-compose-up.ps1" -Build %*
if errorlevel 1 (
    echo  [FAILED] Docker Desktop / stop-dev.bat 후 재시도
    pause
    goto MENU
)
echo.
echo  Stop: 메뉴 4
pause
goto MENU

:RUN_DOCKER_DOWN
echo.
echo  [4] Stopping Docker stack (krstock)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\docker-compose-up.ps1" -Down
echo.
echo  Local :8000/:3000 은 메뉴 5 (stop-dev)
pause
goto MENU

:RUN_STOP_DEV
call "%~dp0stop-dev.bat"
goto MENU

:E2E_ALL
call :E2E_PREP
if errorlevel 1 goto AFTER_E2E
call npm run test:e2e
set "E2E_EC=%ERRORLEVEL%"
popd
goto AFTER_E2E

:E2E_STICKY
call :E2E_PREP
if errorlevel 1 goto AFTER_E2E
call npm run test:e2e -- e2e/market-chrome-sticky.spec.ts
set "E2E_EC=%ERRORLEVEL%"
popd
goto AFTER_E2E

:E2E_MOBILE
call :E2E_PREP
if errorlevel 1 goto AFTER_E2E
call npm run test:e2e:mobile-checklist
set "E2E_EC=%ERRORLEVEL%"
popd
goto AFTER_E2E

:E2E_UI_BUNDLE
echo.
echo  [UI QA] sticky E2E + 모바일 viewport 캡처...
call :E2E_PREP
if errorlevel 1 goto AFTER_E2E
call npm run test:e2e -- e2e/market-chrome-sticky.spec.ts
if errorlevel 1 (
    set "E2E_EC=1"
    popd
    goto AFTER_E2E
)
call npm run test:e2e:mobile-checklist
set "E2E_EC=%ERRORLEVEL%"
popd
goto AFTER_E2E

:E2E_PREP
echo  [E2E] Next 3000/3001 정리 ^(API 8000 유지^), PLAYWRIGHT_REUSE_SERVER=0...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev-ports.ps1" -FrontendOnly
if errorlevel 1 (
    echo  [WARN] 3000/3001 일부 점유 — E2E 계속 시도합니다.
)
set "PLAYWRIGHT_REUSE_SERVER=0"
if not exist "%~dp0my-frontend\package.json" (
    echo  [ERROR] my-frontend\package.json 없음
    exit /b 1
)
if not exist "%~dp0my-frontend\node_modules\@playwright\test" (
    echo  [INFO] npm install + Playwright 브라우저 설치...
    pushd "%~dp0my-frontend"
    call npm install
    if errorlevel 1 (
        popd
        exit /b 1
    )
    call npm run test:e2e:install
    popd
)
pushd "%~dp0my-frontend"
exit /b 0

:AFTER_E2E
echo.
if defined E2E_EC (
    if not "%E2E_EC%"=="0" (
        echo  [E2E FAILED] 메뉴 5 후 메뉴 1 ^(또는 3^). 3001 북마크 사용 금지.
    ) else (
        echo  [E2E OK]
    )
) else if errorlevel 1 (
    echo  [E2E FAILED]
) else (
    echo  [E2E OK]
)
set "E2E_EC="
pause
goto MENU
