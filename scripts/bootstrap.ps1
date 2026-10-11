param(
    [Parameter(Position = 0)]
    [string]$InstallDir,
    [string]$Branch,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/merberg-ai/Morphorum.git'

if ($Help) {
    Write-Host ''
    Write-Host '  MORPHORUM - WINDOWS INSTALLER' -ForegroundColor Cyan
    Write-Host '  ------------------------------------------' -ForegroundColor DarkGray
    Write-Host '  bootstrap.bat [-InstallDir PATH] [-Branch NAME] [-Help]' -ForegroundColor White
    Write-Host ''
    Write-Host '  No path supplied: prompt for an install location (default C:\Morphorum).' -ForegroundColor Gray
    Write-Host '  -InstallDir:       install to a specific folder without a prompt.' -ForegroundColor Gray
    Write-Host '  -Branch:           clone/update the selected GitHub branch.' -ForegroundColor Gray
    Write-Host '  -Help:             show this help without installing anything.' -ForegroundColor Gray
    Write-Host ''
    return
}

# This file also runs alone when fetched by bootstrap.bat, so its UI is
# self-contained. Scripts inside a checkout use ui_windows.ps1.
function Section([string]$name) {
    Write-Host ''
    Write-Host "  >> $name" -ForegroundColor Magenta
    Write-Host '  -------------------------------------------------------' -ForegroundColor DarkGray
}
function Step([string]$name) { Write-Host "  [>] $name" -ForegroundColor Cyan }
function Okay([string]$name) { Write-Host "  [+] $name" -ForegroundColor Green }
function Warn([string]$name) { Write-Host "  [!] $name" -ForegroundColor Yellow }
function Detail([string]$label, [string]$value) {
    Write-Host ("  {0,-16}" -f ($label + ':')) -ForegroundColor DarkGray -NoNewline
    Write-Host $value -ForegroundColor White
}

try {
    Write-Host ''
    Write-Host '  __  __  ___  ____  ____  _   _  ___  ____  _   _ __  __' -ForegroundColor Cyan
    Write-Host ' |  \/  |/ _ \|  _ \|  _ \| | | |/ _ \|  _ \| | | |  \/  |' -ForegroundColor Cyan
    Write-Host ' | |\/| | | | | |_) | |_) | |_| | | | | |_) | | | | |\/| |' -ForegroundColor Cyan
    Write-Host ' | |  | | |_| |  _ <|  __/|  _  | |_| |  _ <| |_| | |  | |' -ForegroundColor Cyan
    Write-Host ' |_|  |_|\___/|_| \_\_|   |_| |_|\___/|_| \_\\___/|_|  |_|' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '    LOCAL AI IMAGE + MOTION STUDIO  |  SETUP' -ForegroundColor Magenta
    Write-Host '    -------------------------------------------------------' -ForegroundColor DarkGray

    Section 'INSTALLATION LOCATION'
    Write-Host '  Select where Morphorum, its Python runtime and user data will live.' -ForegroundColor Gray
    $defaultDir = 'C:\Morphorum'
    if ([string]::IsNullOrWhiteSpace($InstallDir)) {
        $defaultDir = if ($env:MORPHORUM_HOME) {
            [Environment]::ExpandEnvironmentVariables($env:MORPHORUM_HOME)
        } else { $defaultDir }
        Write-Host "  Press ENTER to use $defaultDir" -ForegroundColor DarkGray
        $chosen = Read-Host '  Install folder'
        $InstallDir = if ([string]::IsNullOrWhiteSpace($chosen)) { $defaultDir } else { $chosen.Trim().Trim('"') }
    }
    $installRoot = [Environment]::ExpandEnvironmentVariables($InstallDir.Trim().Trim('"'))
    if ($installRoot.StartsWith('~')) {
        $tail = $installRoot.Substring(1).TrimStart([char[]]'\/')
        $installRoot = if ($tail) { Join-Path $HOME $tail } else { $HOME }
    }
    $installRoot = [System.IO.Path]::GetFullPath($installRoot)
    if ($installRoot.TrimEnd('\', '/') -eq [System.IO.Path]::GetPathRoot($installRoot).TrimEnd('\', '/')) {
        throw 'Choose a folder (for example C:\Morphorum), not the drive root.'
    }
    Detail 'Installation' $installRoot
    if ($Branch) { Detail 'Git branch' $Branch }

    Section 'PREREQUISITES'
    $gitExe = (Get-Command git -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    if (-not $gitExe) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Git is missing and winget is not available. Install Git for Windows, then retry.'
        }
        Step 'Git was not found. Installing with Windows Package Manager...'
        & winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Git installation failed. Install Git manually and retry.' }
        $gitCandidates = @(
            "$env:ProgramFiles\Git\cmd\git.exe",
            "$env:LocalAppData\Programs\Git\cmd\git.exe"
        )
        $gitExe = $gitCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $gitExe) {
            throw 'Git was installed but not found in the current session. Open a new terminal and retry.'
        }
    }
    Okay "Git: $(& $gitExe --version)"

    Section 'SOURCE CODE'
    $installParent = Split-Path -Parent $installRoot
    if ($installParent -and -not (Test-Path $installParent)) {
        New-Item -ItemType Directory -Force -Path $installParent | Out-Null
    }
    if (Test-Path (Join-Path $installRoot '.git')) {
        $installManifest = Join-Path $installRoot 'data\install.json'
        $updater = Join-Path $installRoot 'update.bat'
        if ((Test-Path $installManifest) -and (Test-Path $updater)) {
            Step 'Existing Morphorum install found; using the guarded updater.'
            if ($Branch) { & $updater $Branch } else { & $updater }
            if ($LASTEXITCODE -ne 0) { throw "Update failed (exit $LASTEXITCODE)." }
            Okay "Morphorum updated at $installRoot"
            Write-Host "  Launch: $installRoot\run.bat" -ForegroundColor Cyan
            return
        }
        Warn 'Existing checkout found. Resuming interrupted/legacy installation.'
        & $gitExe -C $installRoot pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw 'Unable to pull checkout. Resolve local Git changes first.' }
    } elseif (Test-Path $installRoot) {
        $items = @(Get-ChildItem -Force $installRoot -ErrorAction SilentlyContinue)
        if ($items.Count) { throw "Target directory exists and is not an empty Morphorum checkout: $installRoot" }
        Step 'Cloning the Morphorum repository...'
        if ($Branch) {
            & $gitExe clone --branch $Branch --single-branch $repo $installRoot
        } else {
            & $gitExe clone $repo $installRoot
        }
        if ($LASTEXITCODE -ne 0) { throw 'Git clone failed. Verify connectivity and branch name.' }
    } else {
        Step 'Cloning the Morphorum repository...'
        if ($Branch) {
            & $gitExe clone --branch $Branch --single-branch $repo $installRoot
        } else {
            & $gitExe clone $repo $installRoot
        }
        if ($LASTEXITCODE -ne 0) { throw 'Git clone failed. Verify connectivity and branch name.' }
    }
    Okay 'Source code ready.'

    Section 'PREPARING THE LOCAL AI RUNTIME'
    $installer = Join-Path $installRoot 'install.bat'
    if (-not (Test-Path $installer)) { throw 'Checkout does not contain install.bat.' }
    & $installer
    if ($LASTEXITCODE -ne 0) { throw "Morphorum installer failed (exit $LASTEXITCODE)." }

    Section 'READY'
    Okay 'Morphorum is installed!'
    Detail 'Location' $installRoot
    Write-Host "  Start locally:  $installRoot\run.bat" -ForegroundColor Cyan
    Write-Host "  Start on LAN:  $installRoot\run-lan.bat" -ForegroundColor Cyan
    Write-Host "  Update later:  $installRoot\update.bat" -ForegroundColor Cyan
    Write-Host ''
} catch {
    Write-Host ''
    Write-Host '  [X] INSTALLATION FAILED' -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '  Fix the issue above and run bootstrap.bat again.' -ForegroundColor Yellow
    exit 1
}
