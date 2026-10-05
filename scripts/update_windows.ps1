$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($text) { Write-Host "[Morphorum] $text" -ForegroundColor Cyan }
function Okay($text) { Write-Host "[OK] $text" -ForegroundColor Green }
function Warn($text) { Write-Host "[!] $text" -ForegroundColor Yellow }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required to update Morphorum.'
}

$dirty = git -C $Root status --porcelain --untracked-files=no
if ($dirty) {
    Write-Host '[X] Tracked Morphorum files have local changes. Update aborted to avoid overwriting them.' -ForegroundColor Red
    Write-Host $dirty
    exit 1
}

$previous = (git -C $Root rev-parse HEAD).Trim()
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $Root "backups\update-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Set-Content -Path (Join-Path $backup 'previous_commit.txt') -Value $previous

if (Test-Path (Join-Path $Root 'data\config.yaml')) {
    Copy-Item (Join-Path $Root 'data\config.yaml') (Join-Path $backup 'config.yaml')
}
Get-ChildItem (Join-Path $Root 'data') -Filter '*.db' -ErrorAction SilentlyContinue | ForEach-Object {
    Copy-Item $_.FullName $backup
}

Step "Backup created: $backup"
Step 'Pulling Morphorum update...'
git -C $Root pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

try {
    & (Join-Path $Root 'scripts\install_windows.ps1') -Update
    if ($LASTEXITCODE -ne 0) { throw "installer returned exit code $LASTEXITCODE" }
    Okay 'Morphorum update completed successfully.'
}
catch {
    Warn "Update failed: $($_.Exception.Message)"
    Warn "Rolling source tree back to $previous and restoring the previous runtime dependencies..."
    git -C $Root reset --hard $previous
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[X] Automatic source rollback failed. Run repair.bat after resolving the Git error.' -ForegroundColor Red
        exit 1
    }
    & (Join-Path $Root 'scripts\install_windows.ps1') -Repair
    Write-Host '[X] The update was rolled back. Morphorum should be back on the previous version.' -ForegroundColor Red
    Write-Host "Backup: $backup"
    exit 1
}
