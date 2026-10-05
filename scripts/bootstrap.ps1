param(
    [Parameter(Position = 0)]
    [string]$InstallDir
)

$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/merberg-ai/Morphorum.git'

if ($InstallDir) {
    $installRoot = [Environment]::ExpandEnvironmentVariables($InstallDir)
} elseif ($env:MORPHORUM_HOME) {
    $installRoot = [Environment]::ExpandEnvironmentVariables($env:MORPHORUM_HOME)
} else {
    $installRoot = Join-Path $HOME 'Morphorum'
}

if ($installRoot.StartsWith('~')) {
    $relativeHomePath = $installRoot.Substring(1).TrimStart([char[]]'\/')
    $installRoot = if ($relativeHomePath) { Join-Path $HOME $relativeHomePath } else { $HOME }
}
$installRoot = [System.IO.Path]::GetFullPath($installRoot)

Write-Host ''
Write-Host 'Morphorum bootstrap' -ForegroundColor Cyan
Write-Host '===================' -ForegroundColor Cyan
Write-Host "Install directory: $installRoot"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host 'Git was not found. Installing Git with winget...'
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
        $gitCandidates = @(
            "$env:ProgramFiles\Git\cmd\git.exe",
            "$env:LocalAppData\Programs\Git\cmd\git.exe"
        )
        $gitExe = $gitCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $gitExe) {
            throw 'Git was installed but is not visible yet. Open a new PowerShell window and run the Morphorum install command again.'
        }
    } else {
        throw 'Git is required and neither Git nor winget was found. Install Git, then rerun this command.'
    }
} else {
    $gitExe = (Get-Command git).Source
}

$installParent = Split-Path -Parent $installRoot
if ($installParent -and -not (Test-Path $installParent)) {
    New-Item -ItemType Directory -Force -Path $installParent | Out-Null
}

if (Test-Path (Join-Path $installRoot '.git')) {
    Write-Host 'Existing Morphorum installation found; using guarded updater...' -ForegroundColor Cyan
    $updater = Join-Path $installRoot 'update.bat'
    if (Test-Path $updater) {
        & $updater
        if ($LASTEXITCODE -ne 0) { throw "Morphorum update failed with exit code $LASTEXITCODE." }
        Write-Host ''
        Write-Host "Morphorum is updated at $installRoot" -ForegroundColor Green
        Write-Host "Start it with: $installRoot\run.bat"
        return
    }

    Write-Host 'Legacy checkout has no guarded updater yet; performing one-time fast-forward update.' -ForegroundColor Yellow
    & $gitExe -C $installRoot pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'git pull failed. Local changes may need attention.' }
} elseif (Test-Path $installRoot) {
    $items = Get-ChildItem -Force $installRoot -ErrorAction SilentlyContinue
    if ($items) { throw "Install directory exists and is not a Morphorum git checkout: $installRoot" }
    & $gitExe clone $repo $installRoot
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed.' }
} else {
    & $gitExe clone $repo $installRoot
    if ($LASTEXITCODE -ne 0) { throw 'git clone failed.' }
}

$installer = Join-Path $installRoot 'install.bat'
if (-not (Test-Path $installer)) { throw 'Morphorum checkout does not contain install.bat.' }

Write-Host ''
Write-Host 'Running Morphorum installer...' -ForegroundColor Cyan
& $installer
if ($LASTEXITCODE -ne 0) { throw "Morphorum installer failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host "Morphorum is installed at $installRoot" -ForegroundColor Green
Write-Host "Start it with: $installRoot\run.bat"
