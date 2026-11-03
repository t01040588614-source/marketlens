# MarketLens — Windows 로그인 후 백그라운드 기동 (작업 스케줄러에서 호출)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$startScript = Join-Path $root 'scripts\start-servers.ps1'
$logDir = Join-Path $env:LOCALAPPDATA 'MarketLens'
$logFile = Join-Path $logDir 'autostart.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -Path $logFile -Value "`n========== $stamp logon start ==========" -Encoding UTF8

$params = @{ AutoStart = $true }
if ($env:MARKETLENS_NO_BROWSER -eq '1') {
    $params.NoBrowser = $true
}

try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript @params 2>&1 |
        Tee-Object -FilePath $logFile -Append
    exit $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -Path $logFile -Encoding UTF8
    exit 1
}
