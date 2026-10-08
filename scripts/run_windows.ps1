param(
    [switch]$Lan,
    [int]$Port = 7865
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root '.venv\Scripts\python.exe'

$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'

if (-not (Test-Path $Python)) {
    Write-Host 'Morphorum is not installed yet. Run install.bat first.' -ForegroundColor Yellow
    exit 1
}

$hostAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$displayAddress = if ($Lan) { 'this-computer-ip' } else { '127.0.0.1' }

$branch = ''
if (Get-Command git -ErrorAction SilentlyContinue) {
    try { $branch = (git -C $Root rev-parse --abbrev-ref HEAD).Trim() } catch { $branch = '' }
}
Write-Host "Morphorum starting at http://${displayAddress}:$Port" -ForegroundColor Cyan
if ($branch) {
    Write-Host "Git branch: $branch" -ForegroundColor DarkGray
}
if ($Lan) {
    Write-Host 'LAN mode is enabled. Morphorum will listen on all network interfaces.' -ForegroundColor Yellow
}

& $Python -m morphorum serve --host $hostAddress --port $Port
exit $LASTEXITCODE
