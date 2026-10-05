param(
    [switch]$Repair,
    [switch]$Update,
    [switch]$SkipSelfTest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($text) { Write-Host "[Morphorum] $text" -ForegroundColor Cyan }
function Okay($text) { Write-Host "[OK] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "[!] $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "[X] $text" -ForegroundColor Red }

$RuntimeDir = Join-Path $Root '.runtime'
$UvDir = Join-Path $RuntimeDir 'uv'
$UvExe = Join-Path $UvDir 'uv.exe'
$PythonDir = Join-Path $RuntimeDir 'python'
$UvCache = Join-Path $RuntimeDir 'uv-cache'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'

$env:UV_INSTALL_DIR = $UvDir
$env:UV_NO_MODIFY_PATH = '1'
$env:UV_PYTHON_INSTALL_DIR = $PythonDir
$env:UV_CACHE_DIR = $UvCache
$env:UV_PROJECT_ENVIRONMENT = (Join-Path $Root '.venv')

$dirs = @(
    $RuntimeDir,
    $UvDir,
    $PythonDir,
    $UvCache,
    (Join-Path $Root 'data'),
    (Join-Path $Root 'projects'),
    (Join-Path $Root 'outputs'),
    (Join-Path $Root 'logs'),
    (Join-Path $Root 'cache'),
    (Join-Path $Root 'backups')
)
foreach ($dir in $dirs) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$mode = if ($Repair) { 'repair' } elseif ($Update) { 'update' } else { 'install' }
$logPath = Join-Path $Root "logs\$mode.log"
Start-Transcript -Path $logPath -Append | Out-Null

try {
    Step "Mode: $mode"
    Step "Installation root: $Root"

    try {
        $driveRoot = [System.IO.Path]::GetPathRoot($Root)
        $drive = [System.IO.DriveInfo]::new($driveRoot)
        $freeGiB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
        if ($freeGiB -lt 2) { throw "Only $freeGiB GiB free on $driveRoot. Morphorum needs at least 2 GiB for the base runtime." }
        Okay "Disk space: $freeGiB GiB free"
    } catch {
        if ($_.Exception.Message -like 'Only *') { throw }
        Warn "Could not determine free disk space: $($_.Exception.Message)"
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Step 'Git not found; installing Git with winget...'
            winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw 'Git installation failed.' }
        } else {
            throw 'Git is required and neither Git nor winget is available.'
        }
    } else {
        Okay "$(git --version)"
    }

    if (-not (Test-Path $UvExe)) {
        Step 'Installing Morphorum-owned uv runtime manager...'
        $installer = Invoke-RestMethod 'https://astral.sh/uv/install.ps1'
        Invoke-Expression $installer
        if (-not (Test-Path $UvExe)) { throw "uv installer completed but $UvExe was not found." }
    }
    Okay "uv: $(& $UvExe --version)"

    Step 'Ensuring managed Python 3.12 runtime...'
    & $UvExe python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'uv could not install/find Python 3.12.' }

    if (-not (Test-Path $VenvPython)) {
        Step 'Creating Morphorum virtual environment...'
        & $UvExe venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'uv failed to create .venv.' }
    }

    Step 'Installing/updating Morphorum Python dependencies...'
    & $UvExe pip install --python $VenvPython --upgrade --editable .
    if ($LASTEXITCODE -ne 0) { throw 'Morphorum dependency installation failed.' }
    Okay "Python: $(& $VenvPython --version)"

    $userConfig = Join-Path $Root 'data\config.yaml'
    if (-not (Test-Path $userConfig)) {
        Copy-Item (Join-Path $Root 'config\default.yaml') $userConfig
        Okay 'Created user configuration: data\config.yaml'
    } else {
        Okay 'Existing user configuration preserved.'
    }

    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Step 'FFmpeg not found; installing Gyan.FFmpeg with winget...'
            winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { Warn 'FFmpeg installation failed. Video encoding will not work until FFmpeg is installed.' }
            else { Okay 'FFmpeg installed. A new terminal may be required before its command alias appears.' }
        } else {
            Warn 'FFmpeg not found and winget is unavailable. Video encoding will require FFmpeg.'
        }
    } else {
        Okay 'FFmpeg found.'
    }

    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $gpu = nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
        if ($gpu) { Okay "NVIDIA GPU: $($gpu -join '; ')" } else { Okay 'NVIDIA driver tools detected.' }
    } else {
        Warn 'nvidia-smi not detected. CPU/other backends may still work; NVIDIA rendering will require a supported driver.'
    }

    if (-not $SkipSelfTest) {
        Step 'Running Morphorum API self-test...'
        & $VenvPython -m morphorum self-test
        if ($LASTEXITCODE -ne 0) { throw 'Morphorum self-test failed.' }
        Okay 'API health check passed.'
    }

    Write-Host ''
    Okay 'Morphorum installation is ready.'
    Write-Host "Local launch:  $Root\run.bat"
    Write-Host "LAN launch:    $Root\run-lan.bat"
    Write-Host "Diagnostics:   $Root\repair.bat"
    Write-Host "Log:           $logPath"
}
catch {
    Write-Host ''
    Fail $_.Exception.Message
    Write-Host "Installer log: $logPath"
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch {}
}
