$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$fail = 0
# start.bat / .env.local 과 동일 — 127.0.0.1 고정
$ApiBase = if ($env:STOCK_API_PROXY) { $env:STOCK_API_PROXY.TrimEnd('/') } else { 'http://127.0.0.1:8000' }

function Test-Step($name, [scriptblock]$block) {
    try {
        & $block
        Write-Host "[OK] $name" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $name - $($_.Exception.Message)" -ForegroundColor Red
        $script:fail++
    }
}

function Get-FrontendPage($path, [int]$retries = 3) {
    $url = 'http://127.0.0.1:3000' + $path
    $last = $null
    for ($i = 0; $i -lt $retries; $i++) {
        try {
            return Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 30
        } catch {
            $last = $_
            Start-Sleep -Milliseconds 800
        }
    }
    throw $last.Exception
}

Write-Host "=== MarketLens stack check ===" -ForegroundColor Cyan

Test-Step "Backend health" {
    $h = Invoke-RestMethod "$ApiBase/api/v1/health/" -TimeoutSec 5
    if ($h.status -ne 'healthy') { throw "status=$($h.status)" }
}

Test-Step "Auth email status" {
    Invoke-RestMethod "$ApiBase/api/v1/auth/email/status" -TimeoutSec 5 | Out-Null
}

Test-Step "Tools API" {
    $t = Invoke-RestMethod "$ApiBase/api/v1/tools" -TimeoutSec 5
    if (-not $t.data -or $t.data.Count -lt 3) { throw "tools list empty" }
}

Test-Step "Market cache realtime meta" {
    $c = Invoke-RestMethod "$ApiBase/api/v1/market/cache-status" -TimeoutSec 5
    if (-not $c.realtime_mode) { throw "realtime_mode missing" }
    if ($null -eq $c.ws_push_interval_sec) { throw "ws_push_interval_sec missing" }
}

Test-Step "KIS realtime status endpoint" {
    Invoke-RestMethod "$ApiBase/api/v1/market/kis-realtime" -TimeoutSec 5 | Out-Null
}

Test-Step "Market cache (korea>=1)" {
    $c = Invoke-RestMethod "$ApiBase/api/v1/market/cache-status" -TimeoutSec 5
    if ([int]$c.korea_count -lt 1) { throw "korea_count=$($c.korea_count)" }
}

Test-Step "Korea stocks API" {
    $k = Invoke-RestMethod "$ApiBase/api/v1/stocks/korea" -TimeoutSec 30
    if ($k.Count -lt 1) { throw "empty list" }
}

Test-Step "Stock display names (KR/US official, not ticker-only)" {
    $k = Invoke-RestMethod "$ApiBase/api/v1/stocks/korea/005930" -TimeoutSec 20
    if ($k.name -eq $k.symbol -or $k.name.Length -lt 2) { throw "korea 005930 name=$($k.name)" }
    $u = Invoke-RestMethod "$ApiBase/api/v1/stocks/us" -TimeoutSec 30
    if ($u.Count -lt 1) { throw "empty us list" }
    $jpm = $u | Where-Object { $_.symbol -eq 'JPM' } | Select-Object -First 1
    if (-not $jpm) { throw 'JPM missing in US list' }
    if ($jpm.name -eq 'JPM' -or $jpm.name.Length -lt 8) {
        throw "US name looks like ticker: JPM=$($jpm.name)"
    }
    $asia = Invoke-RestMethod "$ApiBase/api/v1/stocks/asia" -TimeoutSec 30
    $toyota = $asia | Where-Object { $_.symbol -eq '7203' } | Select-Object -First 1
    if ($toyota -and $toyota.name -notlike '*Toyota*') {
        throw "asia 7203 name=$($toyota.name)"
    }
}

Test-Step "Frontend proxy /api/v1/stocks/korea" {
    $r = Invoke-WebRequest "http://127.0.0.1:3000/api/v1/stocks/korea" -UseBasicParsing -TimeoutSec 20
    if ($r.StatusCode -ne 200 -or $r.Content.Length -lt 100) { throw "bad response" }
}

Test-Step "Frontend /markets page" {
    $p = Get-FrontendPage "/markets"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
    if ($p.Content -like '*"statusCode":500*' -or $p.Content -like '*Cannot find module*') {
        throw 'next cache error: stop-dev.bat then run launch bat'
    }
}

Test-Step "Frontend /korea page" {
    $p = Get-FrontendPage "/korea"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
    if ($p.Content -like '*"statusCode":500*' -or $p.Content -like '*Cannot find module*') {
        throw 'next cache error: stop-dev.bat then run launch bat'
    }
    # Dev: /_next/static/css/app/layout.css?v=…  Prod: /_next/static/css/<hash>.css
    if ($p.Content -notmatch 'href="(/_next/static/css/[^"]+\.css[^"]*)"') {
        throw 'CSS bundle link missing'
    }
    $cssPath = $Matches[1]
    $css = Invoke-WebRequest ('http://127.0.0.1:3000' + $cssPath) -UseBasicParsing -TimeoutSec 15
    if ($css.StatusCode -ne 200 -or $css.Content.Length -lt 400) { throw 'CSS empty or 404' }
}

Test-Step "Frontend JS chunks (no ChunkLoadError)" {
    $p = Get-FrontendPage "/markets"
    # dev 청크는 ?v= 쿼리 필수 — 제거하면 404 (main-app.js 등)
    $scripts = [regex]::Matches($p.Content, 'src="(/_next/static/chunks/[^"]+\.js[^"]*)"') |
        ForEach-Object { $_.Groups[1].Value } |
        Select-Object -Unique
    if ($scripts.Count -lt 1) { return }
    $bad = @()
    foreach ($src in ($scripts | Select-Object -First 8)) {
        try {
            $r = Invoke-WebRequest ('http://127.0.0.1:3000' + $src) -UseBasicParsing -TimeoutSec 15
            if ($r.StatusCode -ge 400) { $bad += $src }
        } catch {
            $bad += $src
        }
    }
    if ($bad.Count -gt 0) {
        throw "chunk HTTP error: $($bad[0]) — stop-dev.bat then start.bat -Dev"
    }
}

Test-Step "Integrations hub API" {
    $i = Invoke-RestMethod "$ApiBase/api/v1/integrations" -TimeoutSec 10
    if (-not $i.integrations) { throw "no integrations list" }
}

Test-Step "DOCX stocks API (/api/v1/stocks)" {
    $s = Invoke-RestMethod "$ApiBase/api/v1/stocks?limit=5" -TimeoutSec 30
    if ($null -eq $s) { throw "empty" }
}

Test-Step "Accounts API (PostgreSQL)" {
    try {
        Invoke-RestMethod "$ApiBase/api/v1/accounts?ownerId=user1" -TimeoutSec 15 | Out-Null
    } catch {
        $msg = $_.Exception.Message
        if ($msg -match '500|503|connection|postgres|asyncpg') {
            throw 'DB not ready: Docker db or DATABASE_URL'
        }
        throw
    }
}

Test-Step "Frontend /portfolio" {
    $p = Get-FrontendPage "/portfolio"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
}

Test-Step "Frontend /tools/integrations" {
    $p = Get-FrontendPage "/tools/integrations"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
}

Test-Step "Stock history API (005930 1m)" {
    $h = Invoke-RestMethod "$ApiBase/api/v1/stocks/history?symbol=005930&market=korea&period=1m" -TimeoutSec 45
    if (-not $h.points -or $h.points.Count -lt 5) { throw "too few bars" }
}

Test-Step "News API" {
    $n = Invoke-RestMethod "$ApiBase/api/v1/news" -TimeoutSec 10
    if (-not $n.data -or $n.data.Count -lt 1) { throw "empty news" }
}

Test-Step "Frontend /charts" {
    $p = Get-FrontendPage "/charts"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
}

Test-Step "Frontend /quote/korea/005930" {
    $p = Get-FrontendPage "/quote/korea/005930"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
}

Test-Step "Frontend equity quote critical CSS (mobile sidebar not hidden)" {
    $p = Get-FrontendPage "/quote/korea/005930"
    if ($p.Content -notmatch 'side-slot--aside\{display:block!important') {
        throw 'stale layout CSS — stop-dev.bat then start.bat -Dev (or npm run build for prod/Docker)'
    }
    if ($p.Content -match 'side-slot--rail\{display:none\}\.inv-layout-3col \.inv-side-slot--aside\{display:none') {
        throw 'critical CSS still hides aside on mobile/tablet'
    }
}

Test-Step "Frontend /us" {
    $r = Get-FrontendPage "/us"
    if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
}
Test-Step "Frontend /search" {
    $r = Get-FrontendPage "/search"
    if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
}
Test-Step "Frontend /news" {
    $r = Get-FrontendPage "/news"
    if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
}
Test-Step "Frontend /watchlist" {
    $r = Get-FrontendPage "/watchlist"
    if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
}

Test-Step "Frontend proxy chart history" {
    $r = Invoke-WebRequest "http://127.0.0.1:3000/api/v1/stocks/history?symbol=005930&market=korea&period=1w" -UseBasicParsing -TimeoutSec 45
    if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
}

Test-Step "DOCX /stocks/005930 -> quote redirect" {
    $r = Invoke-WebRequest "http://127.0.0.1:3000/stocks/005930" -UseBasicParsing -TimeoutSec 25 -MaximumRedirection 0 -ErrorAction SilentlyContinue
    if ($r.StatusCode -notin 307, 308, 301, 302) {
        $r2 = Get-FrontendPage "/quote/korea/005930"
        if ($r2.StatusCode -ne 200) { throw "expected redirect or quote 200" }
    }
}

Test-Step "Frontend /charts?symbol=066570 (LG)" {
    $p = Get-FrontendPage "/charts?market=korea&symbol=066570"
    if ($p.StatusCode -ne 200) { throw "status=$($p.StatusCode)" }
}

Test-Step "WebSocket broadcast (verify-realtime-ws.py)" {
    $py = Join-Path $ProjectRoot 'stock-backend\venv\Scripts\python.exe'
    $wsScript = Join-Path $ProjectRoot 'scripts\verify-realtime-ws.py'
    if (-not (Test-Path $py)) { throw "venv python missing" }
    if (-not (Test-Path $wsScript)) { throw "verify-realtime-ws.py missing" }
    & $py $wsScript
    if ($LASTEXITCODE -ne 0) { throw "WS probe exit $LASTEXITCODE" }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host 'All checks passed.' -ForegroundColor Green
    exit 0
}
Write-Host ("{0} check(s) failed — run stop-dev.bat then start again." -f $fail) -ForegroundColor Yellow
exit 1
