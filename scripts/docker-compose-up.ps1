param(
    [switch]$Build,
    [switch]$Down,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch { }

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$envExample = Join-Path $root ".env.example"
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Created .env from .env.example"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker CLI not found. Install Docker Desktop." -ForegroundColor Red
    exit 1
}

function Test-DockerEngine {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    docker info *> $null
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $prev
    return $ok
}

function Wait-DockerEngine {
    param([int]$TimeoutSeconds = 180)

    if (Test-DockerEngine) { return $true }

    $dockerDesktop = Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktop)) {
        Write-Host "[ERROR] Docker engine is not running. Install/start Docker Desktop, then retry." -ForegroundColor Red
        return $false
    }

    Write-Host "Docker engine is off — starting Docker Desktop..."
    Start-Process $dockerDesktop | Out-Null

    for ($elapsed = 0; $elapsed -lt $TimeoutSeconds; $elapsed += 3) {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) {
            Write-Host "Docker engine is ready."
            return $true
        }
        if ($elapsed -gt 0 -and ($elapsed % 15 -eq 0)) {
            Write-Host "  Still waiting for Docker... (${elapsed}s / ${TimeoutSeconds}s)"
        }
    }

    Write-Host "[ERROR] Docker did not become ready in time. Open Docker Desktop manually, wait until it says Running, then run this again." -ForegroundColor Red
    return $false
}

if (-not (Wait-DockerEngine)) { exit 1 }

function Test-LocalPortListen {
    param([int]$Port)
    try {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    } catch {
        return $false
    }
}

function Start-MarketsBrowser {
    param([string]$Url = "http://127.0.0.1:3000/markets")
    Write-Host "Opening browser: $Url" -ForegroundColor Cyan
    try {
        Start-Process $Url | Out-Null
        return $true
    } catch {
        cmd /c start "" $Url | Out-Null
        return $true
    }
}

function Test-WebContainerRunning {
    $id = docker compose ps web --status running -q 2>$null
    return [bool]$id
}

$env:COMPOSE_PROJECT_NAME = "krstock"

if ($Down) {
    docker compose down
    exit $LASTEXITCODE
}

$args = @("compose", "up")
if ($Build) { $args += "--build" }
$args += @("-d", "db", "api", "web")

foreach ($port in @(8000, 3000)) {
    if (Test-LocalPortListen -Port $port) {
        $owned = docker compose ps --format "{{.Service}} {{.Ports}}" 2>$null
        if ($owned -notmatch ":$port->") {
            Write-Host "[WARN] Port $port is already in use (local dev?). Run stop-dev.bat or 통합.bat menu 4 (Docker stop), then retry." -ForegroundColor Yellow
        }
    }
}

Write-Host "docker $($args -join ' ') ..."
& docker @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] docker compose failed. If ports 8000/3000 are busy, run stop-dev.bat first." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Waiting for API health..."
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 5
        if ($h.status -eq "healthy") {
            $ok = $true
            break
        }
    } catch { }
    Start-Sleep -Seconds 2
}

if (-not $ok) {
    Write-Host "[WARN] API not healthy yet — check: docker compose logs api" -ForegroundColor Yellow
} else {
    Write-Host "API OK"
    $warmupQuotes = Join-Path $root "scripts\warmup-quotes.ps1"
    if (Test-Path $warmupQuotes) {
        Write-Host "Warming quote cache (official company names)..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $warmupQuotes -ApiBase "http://localhost:8000"
    }
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/integrations/apply" -Method Post -TimeoutSec 45 | Out-Null
        Write-Host "integrations/apply OK (API keys + quotes)"
    } catch {
        Write-Host "[NOTE] integrations/apply skipped (may still be warming up)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Waiting for Web /markets..."
$webOk = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $page = Invoke-WebRequest -Uri "http://127.0.0.1:3000/markets" -UseBasicParsing -TimeoutSec 15
        if ($page.StatusCode -eq 200 -and $page.Content -notmatch 'Cannot find module|"statusCode"\s*:\s*500') {
            $webOk = $true
            break
        }
    } catch { }
    Start-Sleep -Seconds 2
}
if ($webOk) {
    Write-Host "Web OK"
} else {
    Write-Host "[WARN] Web not ready — docker compose logs web" -ForegroundColor Yellow
}

$verifyScript = Join-Path $root "scripts\verify-stack.ps1"
if ($ok -and $webOk -and (Test-Path $verifyScript)) {
    Write-Host ""
    Write-Host "Running verify-stack.ps1..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Some checks failed — try: docker compose up --build -d" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "  Web:     http://127.0.0.1:3000/markets"
Write-Host "  API:     http://127.0.0.1:8000/docs"
Write-Host "  Stop:    주식대시보드_통합.bat menu 4  or  docker compose down"
Write-Host "  Local:   stop-dev.bat (if you also run 통합.bat menu 1)"
Write-Host ""

if (-not $NoBrowser) {
    if ($webOk) {
        Start-MarketsBrowser | Out-Null
    } elseif (Test-WebContainerRunning) {
        Write-Host "[WARN] /markets not ready yet — opening browser anyway (refresh in a few seconds)." -ForegroundColor Yellow
        Start-Sleep -Seconds 4
        Start-MarketsBrowser | Out-Null
    } else {
        Write-Host "[ERROR] Web container is not running. See: docker compose logs web" -ForegroundColor Red
        Write-Host "  Manual URL: http://127.0.0.1:3000/markets"
    }
}
