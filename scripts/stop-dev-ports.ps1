# Local dev — FastAPI :8000 + Next :3000/:3001 (start-servers.ps1 와 동일 포트)
param(
    [switch]$FrontendOnly
)
$ErrorActionPreference = 'SilentlyContinue'

function Get-ListenersOnPort {
    param([int]$Port)
    $pids = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    # Get-NetTCPConnection 만으로 PID가 안 잡히는 좀비 리스너 대비
    $netstat = netstat -ano 2>$null
    if ($netstat) {
        foreach ($line in $netstat) {
            if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                $pids += [int]$Matches[1]
            }
        }
    }
    @($pids | Where-Object { $_ -gt 0 } | Select-Object -Unique)
}

function Stop-PortListener {
    param([int]$Port)
    foreach ($procId in (Get-ListenersOnPort -Port $Port)) {
        taskkill /F /T /PID $procId 2>$null | Out-Null
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-StockBackendPython {
    Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            ($cmd -match 'stock-backend' -and $cmd -match 'uvicorn') -or
                ($cmd -match 'app\.main:app' -and $cmd -match '8000')
        } |
        ForEach-Object {
            taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

if ($FrontendOnly) {
    Write-Host 'Stopping Next only: 3000/3001 (API 8000 유지)...'
} else {
    Write-Host 'Stopping local listeners: 8000 (API), 3000/3001 (Next)...'
}

for ($pass = 1; $pass -le 3; $pass++) {
    if (-not $FrontendOnly) {
        Stop-PortListener 8000
        Stop-StockBackendPython
    }
    Stop-PortListener 3000
    Stop-PortListener 3001
    Start-Sleep -Milliseconds 350
}

$ports = if ($FrontendOnly) { @(3000, 3001) } else { @(8000, 3000, 3001) }
$anyBusy = $false
foreach ($port in $ports) {
    $listen = Get-ListenersOnPort -Port $port
    if ($listen.Count -gt 0) {
        $anyBusy = $true
        Write-Host "  [WARN] Port $port still listening (PID $($listen -join ','))" -ForegroundColor Yellow
        if ($port -eq 8000) {
            Write-Host '         Docker가 8000을 쓰면 통합.bat 메뉴 4 (Docker 중지).' -ForegroundColor Yellow
            Write-Host '         Stock Backend cmd 창이 열려 있으면 창을 닫은 뒤 다시 실행하세요.' -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [OK]   Port $port free"
    }
}

if (-not $anyBusy) {
    if ($FrontendOnly) {
        Write-Host 'Done — Next dev/prod stopped (API unchanged).'
    } else {
        Write-Host 'Done — local FastAPI + Next dev/prod stopped.'
    }
    exit 0
}

Write-Host 'Some ports still busy — 위 안내 확인 후 재시도.'
exit 1
