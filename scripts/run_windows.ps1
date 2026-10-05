param([switch]$Lan)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host 'Morphorum environment is not installed. Run install.bat first.' -ForegroundColor Yellow
    exit 1
}

if (Test-Path 'app\main.py') {
    $env:MORPHORUM_HOST_OVERRIDE = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
    & $python -m app.main
    exit $LASTEXITCODE
}

Write-Host 'Morphorum application server has not landed yet; this repository currently contains the project foundation.' -ForegroundColor Yellow
Write-Host 'See docs\ROADMAP.md for the implementation milestones.'
exit 2
