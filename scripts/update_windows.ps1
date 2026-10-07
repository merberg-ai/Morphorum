param(
    [Parameter(Position = 0)]
    [string]$Branch
)

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
$previousBranch = (git -C $Root rev-parse --abbrev-ref HEAD).Trim()
$targetBranch = if ($Branch) { $Branch.Trim() } else { $previousBranch }

if (-not $targetBranch -or $targetBranch -eq 'HEAD') {
    throw 'Morphorum is in detached HEAD state. Specify a branch explicitly, for example: update.bat main'
}

if ($Branch) {
    Step "Fetching branch information from origin..."
    git -C $Root fetch origin --prune
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    git -C $Root show-ref --verify --quiet "refs/remotes/origin/$targetBranch"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote branch 'origin/$targetBranch' was not found."
    }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $Root "backups\update-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Set-Content -Path (Join-Path $backup 'previous_commit.txt') -Value $previous
Set-Content -Path (Join-Path $backup 'previous_branch.txt') -Value $previousBranch

if (Test-Path (Join-Path $Root 'data\config.yaml')) {
    Copy-Item (Join-Path $Root 'data\config.yaml') (Join-Path $backup 'config.yaml')
}
Get-ChildItem (Join-Path $Root 'data') -Filter '*.db' -ErrorAction SilentlyContinue | ForEach-Object {
    Copy-Item $_.FullName $backup
}

Step "Backup created: $backup"

try {
    if ($targetBranch -ne $previousBranch) {
        Step "Switching Morphorum from '$previousBranch' to '$targetBranch'..."
        git -C $Root show-ref --verify --quiet "refs/heads/$targetBranch"
        if ($LASTEXITCODE -eq 0) {
            git -C $Root switch $targetBranch
        }
        else {
            git -C $Root switch --track -c $targetBranch "origin/$targetBranch"
        }
        if ($LASTEXITCODE -ne 0) {
            throw "git switch returned exit code $LASTEXITCODE"
        }
    }

    Step "Updating branch '$targetBranch'..."
    git -C $Root pull --ff-only origin $targetBranch
    if ($LASTEXITCODE -ne 0) {
        throw "git pull returned exit code $LASTEXITCODE"
    }

    & (Join-Path $Root 'scripts\install_windows.ps1') -Update
    if ($LASTEXITCODE -ne 0) { throw "installer returned exit code $LASTEXITCODE" }
    Okay "Morphorum update completed successfully on branch '$targetBranch'."
}
catch {
    Warn "Update failed: $($_.Exception.Message)"
    Warn "Rolling source tree back to branch '$previousBranch' at $previous and restoring the previous runtime dependencies..."

    if ($previousBranch -and $previousBranch -ne 'HEAD') {
        git -C $Root switch $previousBranch
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[X] Automatic branch rollback failed. Resolve the Git error, then run repair.bat.' -ForegroundColor Red
            exit 1
        }
    }
    else {
        git -C $Root checkout --detach $previous
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[X] Automatic detached-HEAD rollback failed. Resolve the Git error, then run repair.bat.' -ForegroundColor Red
            exit 1
        }
    }

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
