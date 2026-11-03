param(
    [switch]$Clean,
    [switch]$SkipClean,
    [switch]$Dev,
    # 프로덕션(npm run build + start) — Dev와 반대
    [switch]$Prod,
    # Windows 로그인 자동 기동 — Enter 대기 없음, .next 유지, 빌드 있으면 생략
    [switch]$AutoStart,
    [switch]$NoBrowser
)

if ($Prod) { $Dev = $false }

if ($AutoStart -and -not $Clean -and -not $SkipClean) {
    $SkipClean = $true
}

$ErrorActionPreference = 'Continue'
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch { }

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'stock-backend'
$frontend = Join-Path $root 'my-frontend'
$venvPy = Join-Path $backend 'venv\Scripts\python.exe'
$venvPip = Join-Path $backend 'venv\Scripts\pip.exe'
$verifyScript = Join-Path $root 'scripts\verify-stack.ps1'

function Pause-IfInteractive([string]$Message = 'Press Enter to close') {
    if (-not $AutoStart) {
        Read-Host $Message
    }
}

function Test-FrontendBuildPresent {
    return Test-Path (Join-Path $frontend '.next\BUILD_ID')
}

function Test-FrontendBuildStale {
    $buildIdPath = Join-Path $frontend '.next\BUILD_ID'
    if (-not (Test-Path $buildIdPath)) { return $true }
    $buildTime = (Get-Item $buildIdPath).LastWriteTime
    $srcRoot = Join-Path $frontend 'src'
    if (-not (Test-Path $srcRoot)) { return $false }
    $newer = Get-ChildItem $srcRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $buildTime } |
        Select-Object -First 1
    return ($null -ne $newer)
}

function Test-FrontendJsChunks([string]$PagePath = '/markets') {
    try {
        $page = Invoke-WebRequest -Uri ("http://127.0.0.1:3000" + $PagePath) -UseBasicParsing -TimeoutSec 25
        if ($page.StatusCode -ne 200) { return $false }
        $scripts = [regex]::Matches($page.Content, 'src="(/_next/static/chunks/[^"]+\.js[^"]*)"') |
            ForEach-Object { $_.Groups[1].Value } |
            Select-Object -Unique
        if ($scripts.Count -lt 1) { return $true }
        $checked = 0
        foreach ($src in ($scripts | Select-Object -First 10)) {
            $checked++
            $url = 'http://127.0.0.1:3000' + $src
            try {
                $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15
                if ($r.StatusCode -ge 400) { return $false }
            } catch {
                return $false
            }
        }
        return ($checked -gt 0)
    } catch {
        return $false
    }
}

function Open-DashboardBrowser {
    if ($NoBrowser) { return }
    $url = 'http://127.0.0.1:3000/markets'
    Write-Host "Opening browser: $url" -ForegroundColor Cyan
    try {
        Start-Process $url | Out-Null
    } catch {
        cmd /c start "" $url | Out-Null
    }
}

function Stop-PortListener([int]$Port) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id ($_.OwningProcess) -Force -ErrorAction SilentlyContinue }
}

function Test-CommandOnPath([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-BackendDatabaseUrl {
    $envPath = Join-Path $backend '.env'
    if (-not (Test-Path $envPath)) { return '' }
    foreach ($line in Get-Content $envPath -ErrorAction SilentlyContinue) {
        if ($line -match '^\s*DATABASE_URL\s*=\s*(.+)\s*$') {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

function Test-WantFullStack {
    return -not (Test-Path (Join-Path $backend '.use_sqlite'))
}

function Test-DockerEngine {
    if (-not (Test-CommandOnPath 'docker')) { return $false }
    docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-RootDockerEnv {
    $rootEnv = Join-Path $root '.env'
    $rootExample = Join-Path $root '.env.example'
    if (-not (Test-Path $rootEnv) -and (Test-Path $rootExample)) {
        Copy-Item -Path $rootExample -Destination $rootEnv
        Write-Host '  Created root .env (docker compose Postgres)'
    }
}

function Set-BackendDatabasePostgres {
    $envPath = Join-Path $backend '.env'
    if (-not (Test-Path $envPath)) { return $false }
    $pgUrl = 'postgresql+asyncpg://krstock:krstockpass@localhost:5432/krstock'
    $current = Get-BackendDatabaseUrl
    if ($current -match 'postgresql') { return $false }
    $lines = Get-Content $envPath -Encoding UTF8
    $out = New-Object System.Collections.Generic.List[string]
    $replaced = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*DATABASE_URL\s*=') {
            if (-not $replaced) {
                if ($line -match 'sqlite') {
                    $out.Add("# $line  # auto: full-stack")
                }
                $out.Add("DATABASE_URL=$pgUrl")
                $replaced = $true
            }
        } else {
            $out.Add($line)
        }
    }
    if (-not $replaced) {
        $out.Add("DATABASE_URL=$pgUrl")
    }
    Set-Content -Path $envPath -Value $out -Encoding UTF8
    Write-Host '  DATABASE_URL set to PostgreSQL (accounts, screener, DOCX DB)' -ForegroundColor Cyan
    return $true
}

function Ensure-IntegrationDataDir {
    $dataDir = Join-Path $backend 'data'
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    }
    $example = Join-Path $dataDir 'integration_keys.json.example'
    $target = Join-Path $dataDir 'integration_keys.json'
    if ((Test-Path $example) -and -not (Test-Path $target)) {
        Copy-Item $example $target
        Write-Host '  Created data/integration_keys.json (API keys UI)'
    }
}

function Ensure-BackendEnv {
    $envPath = Join-Path $backend '.env'
    $example = Join-Path $backend '.env.example'
    if (-not (Test-Path $envPath) -and (Test-Path $example)) {
        Copy-Item -Path $example -Destination $envPath
        Write-Host '  Created stock-backend/.env from .env.example'
    }
}

function Ensure-PostgresDocker {
    if (-not (Test-WantFullStack)) {
        Write-Host '  DB: stock-backend\.use_sqlite found — skipping Docker Postgres (quotes API only)'
        return $true
    }
    if (-not (Test-CommandOnPath 'docker')) {
        Write-Host '  [WARN] docker CLI not found — use stock-backend\.use_sqlite or install Docker Desktop' -ForegroundColor Yellow
        return $false
    }
    if (-not (Test-DockerEngine)) {
        Write-Host '  [WARN] Docker Desktop is NOT running (dockerDesktopLinuxEngine pipe missing).' -ForegroundColor Yellow
        Write-Host '         Start Docker Desktop and re-run, OR create stock-backend\.use_sqlite for quotes-only mode.' -ForegroundColor Yellow
        return $false
    }
    $compose = Join-Path $root 'docker-compose.yml'
    if (-not (Test-Path $compose)) {
        Write-Host '  [WARN] docker-compose.yml not found' -ForegroundColor Yellow
        return $false
    }
    Ensure-RootDockerEnv
    Write-Host '  docker compose up -d db (PostgreSQL 16)...'
    Push-Location $root
    $env:COMPOSE_PROJECT_NAME = 'krstock'
    & docker compose -p krstock up -d db 2>&1 | ForEach-Object { Write-Host "  $_" }
    $dockerExit = $LASTEXITCODE
    Pop-Location
    if ($dockerExit -ne 0) {
        Write-Host '  [WARN] Docker DB failed — ensure Docker Desktop is running, then retry' -ForegroundColor Yellow
        return $false
    }
    if (Set-BackendDatabasePostgres) {
        $script:BackendEnvChanged = $true
    }
    $ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue -ErrorAction Stop
            if ($tcp.TcpTestSucceeded) {
                $ready = $true
                break
            }
        } catch { }
        Write-Host "  ... waiting for Postgres ($($i * 2)s)"
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        Write-Host '  [WARN] Postgres port 5432 not ready — DB init may be skipped' -ForegroundColor Yellow
    }
    return $ready
}

function Ensure-FrontendEnv {
    $envPath = Join-Path $frontend '.env.local'
    $example = Join-Path $frontend '.env.local.example'
    $default = @"
# 브라우저는 /api/v1 프록시 사용 (next.config rewrites)
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/api/v1/ws/stocks
STOCK_API_PROXY=http://127.0.0.1:8000

# 자동 REST 시세 폴링: live | balanced | eco (가격은 WS 우선)
NEXT_PUBLIC_QUOTE_REFRESH_PRESET=live
"@
    if (-not (Test-Path $example)) {
        Set-Content -Path $example -Value $default -Encoding UTF8
    }
    if (-not (Test-Path $envPath)) {
        Write-Host '  Created .env.local (API, WebSocket, live refresh preset)'
        if (Test-Path $example) {
            Copy-Item -Path $example -Destination $envPath
        } else {
            Set-Content -Path $envPath -Value $default -Encoding UTF8
        }
        return
    }
    $required = [ordered]@{
        'NEXT_PUBLIC_QUOTE_REFRESH_PRESET' = 'live'
        'NEXT_PUBLIC_API_URL'              = 'http://127.0.0.1:8000/api/v1'
        'NEXT_PUBLIC_WS_URL'               = 'ws://127.0.0.1:8000/api/v1/ws/stocks'
        'STOCK_API_PROXY'                  = 'http://127.0.0.1:8000'
    }
    $lines = Get-Content $envPath -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $lines) { $lines = @() }
    $present = @{}
    foreach ($line in $lines) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
            $present[$Matches[1]] = $true
        }
    }
    $added = $false
    foreach ($key in $required.Keys) {
        if (-not $present.ContainsKey($key)) {
            $lines += "$key=$($required[$key])"
            $added = $true
        }
    }
    if ($added) {
        Set-Content -Path $envPath -Value $lines -Encoding UTF8
        Write-Host '  Patched .env.local (missing realtime keys added)' -ForegroundColor Cyan
    }

    $normalized = $false
    $out = foreach ($line in (Get-Content $envPath -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        if ($line -match '^\s*(NEXT_PUBLIC_API_URL|NEXT_PUBLIC_WS_URL|STOCK_API_PROXY)\s*=\s*(.+)\s*$') {
            $key = $Matches[1]
            $val = $Matches[2].Trim()
            if ($val -match 'localhost') {
                $normalized = $true
                "$key=$($val -replace 'localhost','127.0.0.1')"
                continue
            }
        }
        $line
    }
    if ($normalized) {
        Set-Content -Path $envPath -Value $out -Encoding UTF8
        Write-Host '  Normalized .env.local localhost -> 127.0.0.1 (API/WS/proxy)' -ForegroundColor Cyan
    }
}

function Test-BackendReady {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 8
        if ($health.status -ne 'healthy') { return $false }
        $cache = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/market/cache-status' -TimeoutSec 8
        return ([int]$cache.korea_count -ge 1)
    } catch {
        return $false
    }
}

function Test-FrontendReady {
    try {
        $page = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/markets' -UseBasicParsing -TimeoutSec 20
        if ($page.StatusCode -ne 200) { return $false }
        $html = $page.Content
        if ($html -match '"statusCode"\s*:\s*500' -or $html -match 'Cannot find module') { return $false }
        if ($html -match 'missing required error components') { return $false }
        if ($html -notmatch 'app-main|desktop-header|critical-layout') { return $false }
        if ($html -notmatch 'app-market-chrome-sticky--with-ticker') { return $false }
        if ($html -match 'href="(/_next/static/css/[^"]+\.css)') {
            $cssUrl = 'http://127.0.0.1:3000' + $Matches[1]
            $css = Invoke-WebRequest -Uri $cssUrl -UseBasicParsing -TimeoutSec 12
            if ($css.StatusCode -ne 200 -or $css.Content.Length -lt 400) { return $false }
            if ($css.Content -notmatch '--page-background|\.container') { return $false }
            return $true
        }
        return ($html.Length -gt 2000)
    } catch {
        return $false
    }
}

function Start-BackendProcess([bool]$UseDev) {
    $reloadFlag = if ($UseDev) { ' --reload' } else { '' }
    $backendCmd = "cd /d `"$backend`" && `"$venvPip`" install -r requirements.txt -q && `"$venvPy`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000$reloadFlag"
    Start-Process cmd.exe -WindowStyle Minimized -ArgumentList @('/k', 'title Stock Backend && ' + $backendCmd) | Out-Null
}

function Start-FrontendProcess([bool]$UseDev) {
    if ($UseDev) {
        $frontendCmd = "cd /d `"$frontend`" && set WATCHPACK_POLLING=true&& npm run dev"
    } else {
        $frontendCmd = "cd /d `"$frontend`" && npm run start"
    }
    Start-Process cmd.exe -WindowStyle Minimized -ArgumentList @('/k', 'title Stock Frontend && ' + $frontendCmd) | Out-Null
}

function Invoke-FrontendBuild {
    Write-Host '  Next.js production build (1-2 min)...'
    Push-Location $frontend
    npm run build
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) {
        Write-Host '  [ERROR] npm run build failed — check Stock Frontend window' -ForegroundColor Red
        Pause-IfInteractive
        exit 1
    }
}

function Invoke-BackendWarmup {
    if (-not (Test-BackendReady)) { return }
    $warmupQuotes = Join-Path $root 'scripts\warmup-quotes.ps1'
    if (Test-Path $warmupQuotes) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $warmupQuotes -ApiBase 'http://localhost:8000'
    }
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/integrations/apply' -Method Post -TimeoutSec 30 | Out-Null
        Write-Host '  integrations/apply completed (API keys and quotes)'
    } catch {
        Write-Host '  [NOTE] skipped integrations/apply (backend may still be warming up)'
    }
}

function Start-BackgroundDocxSeed {
    if (-not (Test-WantFullStack)) { return }
    $dbUrl = Get-BackendDatabaseUrl
    if ($dbUrl -notmatch 'postgresql') { return }
    $marker = Join-Path $backend 'data\.full_stack_seeded'
    if (Test-Path $marker) { return }
    $seedCmd = "cd /d `"$backend`" && `"$venvPy`" scripts\ingest_docx_all.py --max-codes 40 && echo ok>data\.full_stack_seeded"
    Start-Process cmd.exe -WindowStyle Minimized -ArgumentList @('/c', 'title DOCX ETL && ' + $seedCmd) | Out-Null
    Write-Host '  [background] DOCX ETL started (first run, max 40 symbols)'
}

function Write-FeatureLinks {
    Write-Host '  Quick links:'
    Write-Host '    Markets    http://127.0.0.1:3000/markets'
    Write-Host '    Stocks     http://127.0.0.1:3000/stocks'
    Write-Host '    Portfolio  http://127.0.0.1:3000/portfolio'
    Write-Host '    API keys   http://127.0.0.1:3000/tools/integrations'
    Write-Host '    Swagger    http://127.0.0.1:8000/docs'
}

$script:BackendEnvChanged = $false

function Wait-ServersReady([int]$MaxIterations) {
    $backendOk = $false
    $frontendOk = $false
    for ($i = 0; $i -lt $MaxIterations; $i++) {
        if (-not $backendOk) { $backendOk = Test-BackendReady }
        if ($backendOk -and -not $frontendOk) { $frontendOk = Test-FrontendReady }
        if ($backendOk -and $frontendOk) { break }
        $bStat = if ($backendOk) { 'OK' } else { 'wait' }
        $fStat = if ($frontendOk) { 'OK' } else { 'wait' }
        Write-Host "  ... $($i * 2)s (backend:$bStat frontend:$fStat)"
        Start-Sleep -Seconds 2
    }
    return @{ Backend = $backendOk; Frontend = $frontendOk }
}

Write-Host '=========================================='
Write-Host ' MarketLens — starting stack'
if ($AutoStart) { Write-Host ' (auto-start mode)' }
Write-Host '=========================================='
Write-Host ''

Write-Host '[1/9] Tools (Python, Node; Docker recommended)...'
if (-not (Test-CommandOnPath 'python')) {
    Write-Host '  [ERROR] python not found — install Python 3.11+ and add to PATH' -ForegroundColor Red
    Pause-IfInteractive
    exit 1
}
if (-not (Test-CommandOnPath 'npm')) {
    Write-Host '  [ERROR] npm not found — install Node.js 18+' -ForegroundColor Red
    Pause-IfInteractive
    exit 1
}

Write-Host '[2/9] Free ports 8000, 3000 and 3001...'
Stop-PortListener 8000
Stop-PortListener 3000
Stop-PortListener 3001
Start-Sleep -Seconds 1

Write-Host '[3/9] Environment (.env, Postgres, venv, npm)...'
Ensure-BackendEnv
Ensure-IntegrationDataDir
Ensure-PostgresDocker | Out-Null
if (-not (Test-Path $venvPy)) {
    Write-Host '  Creating Python venv...'
    Push-Location $backend
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  [ERROR] venv creation failed — check Python 3.11+' -ForegroundColor Red
        Pause-IfInteractive
        exit 1
    }
    Pop-Location
}
Ensure-FrontendEnv
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Write-Host '  npm install (first time)...'
    Push-Location $frontend
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  [ERROR] npm install failed' -ForegroundColor Red
        Pop-Location
        Pause-IfInteractive
        exit 1
    }
    Pop-Location
}

if ($Clean -or -not $SkipClean) {
    Write-Host '  Clearing .next cache (avoids broken clicks/CSS)...'
    Remove-Item -Recurse -Force (Join-Path $frontend '.next') -ErrorAction SilentlyContinue
}

Write-Host '[4/9] Start backend and frontend...'
if ($Dev) {
    Write-Host '  Dev mode: save files to hot-reload (Fast Refresh / uvicorn --reload)' -ForegroundColor Cyan
    if (Test-FrontendBuildPresent) {
        Write-Host '  Dev mode: removing production .next (dev/prod chunk conflict 방지)...' -ForegroundColor Cyan
        Remove-Item -Recurse -Force (Join-Path $frontend '.next') -ErrorAction SilentlyContinue
    }
}
Start-BackendProcess -UseDev:$Dev
Start-Sleep -Seconds 3
if (-not $Dev) {
    $reuseProdBuild = $false
    if ($AutoStart -and (Test-FrontendBuildPresent) -and -not (Test-FrontendBuildStale)) {
        $reuseProdBuild = $true
        Write-Host '  AutoStart: reusing existing Next.js build (npm run start)'
    }
    if (-not $reuseProdBuild) {
        if ((Test-FrontendBuildPresent) -and (Test-FrontendBuildStale)) {
            Write-Host '  Source changed since last build — rebuilding Next.js...' -ForegroundColor Cyan
        }
        Invoke-FrontendBuild
    }
} else {
    Write-Host '  npm run dev (hot reload, no build step)'
}
Start-FrontendProcess -UseDev:$Dev

Write-Host '[5/9] Wait for ready (quotes ~30-90s, up to 4 min)...'
$status = Wait-ServersReady -MaxIterations 120

if (-not $status.Frontend -and $status.Backend) {
    Write-Host '[4b] Frontend not ready — clearing .next and restarting...'
    Stop-PortListener 3000
    Stop-PortListener 3001
    Start-Sleep -Seconds 2
    Remove-Item -Recurse -Force (Join-Path $frontend '.next') -ErrorAction SilentlyContinue
    if (-not $Dev) { Invoke-FrontendBuild }
    Start-FrontendProcess -UseDev:$Dev
    Start-Sleep -Seconds 8
    $retry = Wait-ServersReady -MaxIterations 90
    if ($retry.Frontend) { $status.Frontend = $true }
}

if ($status.Frontend -and -not (Test-FrontendJsChunks '/markets')) {
    Write-Host '[4c] JS chunks 400/404 (stale .next) — rebuilding frontend...' -ForegroundColor Yellow
    Stop-PortListener 3000
    Stop-PortListener 3001
    Start-Sleep -Seconds 2
    Remove-Item -Recurse -Force (Join-Path $frontend '.next') -ErrorAction SilentlyContinue
    if (-not $Dev) { Invoke-FrontendBuild }
    Start-FrontendProcess -UseDev:$Dev
    Start-Sleep -Seconds 8
    $chunkRetry = Wait-ServersReady -MaxIterations 90
    if (-not $chunkRetry.Frontend) { $status.Frontend = $false }
    elseif (-not (Test-FrontendJsChunks '/markets')) {
        Write-Host '  [WARN] JS chunks still failing — run stop-dev.bat then start.bat -Dev' -ForegroundColor Yellow
    }
}

Write-Host '[6/9] Warmup (integrations apply)...'
Invoke-BackendWarmup
Start-BackgroundDocxSeed

Write-Host '[7/9] verify-stack.ps1...'
$verifyOk = $false
if ($status.Backend -and $status.Frontend -and (Test-Path $verifyScript)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript
    if ($LASTEXITCODE -eq 0) { $verifyOk = $true }
} elseif (-not (Test-Path $verifyScript)) {
    Write-Host '  verify-stack.ps1 missing — using HTTP ready checks only'
    $verifyOk = ($status.Backend -and $status.Frontend)
}

Write-Host '[8/9] verify-realtime.ps1 (WS push)...'
$realtimeOk = $false
$realtimeScript = Join-Path $root 'scripts\verify-realtime.ps1'
if ($status.Backend -and (Test-Path $realtimeScript)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $realtimeScript
    if ($LASTEXITCODE -eq 0) { $realtimeOk = $true }
    else {
        Write-Host '  [WARN] Realtime/WS check failed — UI falls back to REST polling' -ForegroundColor Yellow
    }
} else {
    $realtimeOk = $status.Backend
}

Write-Host '[9/9] Done...'
if ($status.Backend -and $status.Frontend -and $verifyOk -and $realtimeOk) {
    Write-Host ''
    Write-Host 'All services ready.' -ForegroundColor Green
    Write-FeatureLinks
    Write-Host ''
    Write-Host 'Stop: stop-dev.bat'
    Open-DashboardBrowser
    exit 0
}

Write-Host ''
Write-Host 'Some steps did not complete.' -ForegroundColor Yellow
Write-Host "  Backend:  $(if ($status.Backend) { 'OK' } else { 'wait/error — check Stock Backend window' })"
Write-Host "  Frontend: $(if ($status.Frontend) { 'OK' } else { 'wait/error — check Stock Frontend window' })"
Write-Host "  Verify:   $(if ($verifyOk) { 'OK' } else { 'failed — run scripts\verify-stack.ps1' })"
Write-Host "  Realtime: $(if ($realtimeOk) { 'OK (WS + LiveStockQuerySync)' } else { 'WARN — scripts\verify-realtime.ps1' })"
Write-Host '  Broken CSS: run stop-dev.bat then start again (.next rebuild)'
Write-Host '  Manual check: http://127.0.0.1:8000/api/v1/market/cache-status'
if ($status.Backend) {
    Open-DashboardBrowser
}
Pause-IfInteractive
exit 1
