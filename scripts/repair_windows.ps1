$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host 'Morphorum Doctor' -ForegroundColor Cyan
Write-Host '===============' -ForegroundColor Cyan

$checks = @(
    @{ Name='Git'; Command='git'; Args=@('--version') },
    @{ Name='FFmpeg'; Command='ffmpeg'; Args=@('-version') },
    @{ Name='NVIDIA tools'; Command='nvidia-smi'; Args=@('--query-gpu=name,memory.total';'--format=csv,noheader') }
)
foreach ($check in $checks) {
    if (Get-Command $check.Command -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $($check.Name)" -ForegroundColor Green
    } else {
        Write-Host "[!] $($check.Name) not found" -ForegroundColor Yellow
    }
}

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    Write-Host "[OK] Python virtual environment" -ForegroundColor Green
    & $venvPython --version
    & $venvPython -c "import sys; print('Python:', sys.executable)"
    try { & $venvPython -c "import torch; print('PyTorch:', torch.__version__, 'CUDA:', torch.cuda.is_available())" } catch { Write-Host '[!] PyTorch not installed yet.' -ForegroundColor Yellow }
} else {
    Write-Host '[!] Python virtual environment missing.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Running installer in repair mode...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'install_windows.ps1') -Repair
