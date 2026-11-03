$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$fail = 0

function Step($name, [scriptblock]$block) {
    Write-Host ">> $name" -ForegroundColor Cyan
    try {
        & $block
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        Write-Host "[OK] $name" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $name — $($_.Exception.Message)" -ForegroundColor Red
        $script:fail++
    }
}

Step "Frontend lint + typecheck" {
    Push-Location (Join-Path $root 'my-frontend')
    npm run check
    Pop-Location
}

Step "Backend ruff" {
    $py = Join-Path $root 'stock-backend\venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { throw "venv missing — run stock-backend setup first" }
    & $py -m ruff check (Join-Path $root 'stock-backend\app') (Join-Path $root 'stock-backend\tests')
}

Step "Backend pytest" {
    Push-Location (Join-Path $root 'stock-backend')
    & .\venv\Scripts\python.exe -m pytest tests -q --tb=no
    Pop-Location
}

Step "Frontend E2E smoke (3000 + 8000)" {
    $stackUp = $false
    try {
        $null = Invoke-WebRequest 'http://127.0.0.1:3000/markets' -UseBasicParsing -TimeoutSec 5
        $h = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health/' -TimeoutSec 5
        if ($h.status -eq 'healthy') { $stackUp = $true }
    } catch { }
    if (-not $stackUp) {
        Write-Host '  [skip] Full stack not up — run start.bat -Dev then re-run check-all for E2E' -ForegroundColor DarkYellow
        return
    }
    Push-Location (Join-Path $root 'my-frontend')
    $env:PLAYWRIGHT_SKIP_WEBSERVER = '1'
    npx playwright test e2e/smoke.spec.ts e2e/market-chrome-sticky.spec.ts
    Remove-Item Env:PLAYWRIGHT_SKIP_WEBSERVER -ErrorAction SilentlyContinue
    Pop-Location
}

if ($fail -gt 0) {
    Write-Host "`n$fail step(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host "`nAll static checks passed." -ForegroundColor Green
