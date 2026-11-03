# Gmail 등 — .bat/.ps1 제외한 소스 zip (바탕화면)
$ErrorActionPreference = 'Stop'
$src = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desktop = [Environment]::GetFolderPath('Desktop')
$zipPath = Join-Path $desktop 'MarketLens-krstock-email-share.zip'
$staging = Join-Path $env:TEMP 'krstock-email-staging'

if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null

robocopy $src $staging /E `
  /XD node_modules .next venv __pycache__ .pytest_cache .ruff_cache .git .cursor _video_frames .video-frames .vscode `
  /XF .env *.bat *.ps1 *.cmd *.exe backend.err.log backend.out.log `
  /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

$tmpZip = Join-Path $env:TEMP 'krstock-email-pack.zip'
if (Test-Path $tmpZip) { Remove-Item -LiteralPath $tmpZip -Force }
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $tmpZip -CompressionLevel Optimal -Force
Remove-Item -LiteralPath $staging -Recurse -Force
Move-Item -LiteralPath $tmpZip -Destination $zipPath -Force

$mb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
Write-Host "Created: $zipPath ($mb MB)"
