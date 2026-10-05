$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host 'Morphorum Repair / Doctor' -ForegroundColor Cyan
Write-Host '========================' -ForegroundColor Cyan

& (Join-Path $PSScriptRoot 'install_windows.ps1') -Repair
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host '[X] Python environment is still missing after repair.' -ForegroundColor Red
    exit 1
}

Write-Host ''
& $Python -m morphorum doctor
exit $LASTEXITCODE
