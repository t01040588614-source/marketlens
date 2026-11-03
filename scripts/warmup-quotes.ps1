# 시세 캐시·종목 표시명 갱신 (로컬/Docker 공통)
param(
    [string]$ApiBase = $(if ($env:STOCK_API_PROXY) { $env:STOCK_API_PROXY.TrimEnd('/') } else { 'http://localhost:8000' })
)

$ErrorActionPreference = 'Continue'

try {
    Invoke-RestMethod -Uri "$ApiBase/api/v1/market/refresh" -Method Post -TimeoutSec 15 | Out-Null
    Write-Host "  market/refresh requested (quotes + display names)" -ForegroundColor DarkGray
} catch {
    Write-Host "  [NOTE] market/refresh skipped: $($_.Exception.Message)" -ForegroundColor DarkYellow
}

for ($i = 0; $i -lt 45; $i++) {
    try {
        $c = Invoke-RestMethod -Uri "$ApiBase/api/v1/market/cache-status" -TimeoutSec 8
        if ([int]$c.korea_count -ge 1 -and [int]$c.us_count -ge 1) {
            $jpm = Invoke-RestMethod -Uri "$ApiBase/api/v1/stocks/us/JPM" -TimeoutSec 15
            if ($jpm.name -and $jpm.name -ne 'JPM' -and $jpm.name.Length -ge 8) {
                Write-Host "  display names ready (e.g. JPM -> $($jpm.name))" -ForegroundColor DarkGray
                break
            }
        }
    } catch { }
    Start-Sleep -Seconds 2
}
