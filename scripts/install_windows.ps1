param(
    [switch]$Repair,
    [switch]$Update
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($text) { Write-Host "[Morphorum] $text" -ForegroundColor Cyan }
function Okay($text) { Write-Host "[OK] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "[!] $text" -ForegroundColor Yellow }

Step "Installation root: $Root"

if (Get-Command git -ErrorAction SilentlyContinue) { Okay "Git: $((git --version))" } else { Warn 'Git not found.' }

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    try { & py -3.12 -c "import sys; print(sys.executable)" *> $null; if ($LASTEXITCODE -eq 0) { $python = @('py','-3.12') } } catch {}
}
if (-not $python -and (Get-Command python -ErrorAction SilentlyContinue)) { $python = @('python') }

if ($python) {
    $pythonCmd = $python[0]
    $pythonArgs = @()
    if ($python.Count -gt 1) { $pythonArgs = $python[1..($python.Count-1)] }
    $ver = & $pythonCmd @pythonArgs --version
    Okay "Python: $ver"

    if (-not (Test-Path '.venv')) {
        Step 'Creating Python virtual environment...'
        & $pythonCmd @pythonArgs -m venv .venv
    }

    $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        & $venvPython -m pip install --upgrade pip
        if (Test-Path 'requirements.txt') {
            Step 'Installing Python requirements...'
            & $venvPython -m pip install -r requirements.txt
        } elseif (Test-Path 'pyproject.toml') {
            Step 'Installing Morphorum Python package...'
            & $venvPython -m pip install -e .
        } else {
            Warn 'Backend dependency manifest has not landed yet; Python environment is ready.'
        }
    }
} else {
    Warn 'Python was not found. The early repository scaffold can be installed, but rendering will require the supported Python runtime once backend code lands.'
}

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) { Okay "FFmpeg found." } else { Warn 'FFmpeg not found yet. Video encoding will require it once rendering lands.' }
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Okay 'NVIDIA driver tools detected.'
} else {
    Warn 'nvidia-smi not detected. This is fine for repository setup but GPU rendering requires a supported backend/device.'
}

New-Item -ItemType Directory -Force -Path projects,renders,data,logs,cache | Out-Null
Okay 'Runtime directories ready.'

if (Test-Path 'frontend\package.json') {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Step 'Installing frontend dependencies...'
        Push-Location frontend
        npm install
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'frontend build failed.' }
        Pop-Location
        Okay 'Frontend built.'
    } else {
        Warn 'Frontend exists but npm was not found.'
    }
} else {
    Warn 'Frontend application has not landed yet; skipping frontend build.'
}

Write-Host ''
Okay 'Morphorum repository setup is complete.'
if (-not (Test-Path 'app')) { Warn 'This is the initial project scaffold; the runnable application server is not implemented yet.' }
