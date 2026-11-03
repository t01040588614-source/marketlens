$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$fail = 0

function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Bad($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; $script:fail++ }

Write-Host "=== MarketLens realtime check ===" -ForegroundColor Cyan

try {
    $c1 = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/market/cache-status" -TimeoutSec 10
    Write-Ok "Cache korea=$($c1.korea_count) us=$($c1.us_count) age=$($c1.cache_age_seconds)s last=$($c1.last_updated)"
    Write-Host "     krMarketOpen=$($c1.krMarketOpen) usMarketOpen=$($c1.usMarketOpen) ws_push=$($c1.ws_push_interval_sec)s"
    if ($c1.message) { Write-Host "     $($c1.message)" }
} catch {
    Write-Bad "Backend cache-status: $($_.Exception.Message)"
}

try {
    $k = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/stocks/korea" -TimeoutSec 45
    $sam = $k | Where-Object { $_.symbol -eq "005930" } | Select-Object -First 1
    if ($sam) {
        Write-Ok "REST 005930 price=$($sam.price) change=$($sam.changePercent)%"
    } else {
        Write-Warn "005930 not in korea list"
    }
} catch {
    Write-Bad "Korea stocks API: $($_.Exception.Message)"
}

try {
    Invoke-RestMethod "http://127.0.0.1:8000/api/v1/market/refresh" -Method Post -TimeoutSec 10 | Out-Null
    Start-Sleep -Seconds 4
    $c2 = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/market/cache-status" -TimeoutSec 10
    if ($null -ne $c2.cache_age_seconds -and [double]$c2.cache_age_seconds -lt 30) {
        Write-Ok "Refresh pipeline: cache_age=$($c2.cache_age_seconds)s after POST /market/refresh"
    } else {
        Write-Warn "Cache still stale after refresh (age=$($c2.cache_age_seconds)s)"
    }
} catch {
    Write-Bad "Market refresh: $($_.Exception.Message)"
}

$py = Join-Path $ProjectRoot 'stock-backend\venv\Scripts\python.exe'
$wsScript = Join-Path $ProjectRoot 'scripts\verify-realtime-ws.py'
if ((Test-Path $py) -and (Test-Path $wsScript)) {
    & $py $wsScript
    if ($LASTEXITCODE -ne 0) { $fail++ }
} else {
    Write-Bad "Missing $py or verify-realtime-ws.py"
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "Realtime path OK (REST cache + WS ~1s push). UI uses MarketWebSocketProvider on /korea." -ForegroundColor Green
    exit 0
}
Write-Host "Some checks failed ($fail)." -ForegroundColor Yellow
exit 1
