param(
    [Parameter(Position = 0)]
    [string]$Branch
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

. (Join-Path $PSScriptRoot 'ui_windows.ps1')
Show-MorphorumBanner -Mode 'UPDATE'
Write-MorphorumSection 'WORKTREE CHECKS'
Write-MorphorumDetail 'Install folder' $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail 'Git is required to update Morphorum. Install Git for Windows and retry.'
    exit 1
}

$dirty = git -C $Root status --porcelain --untracked-files=no
if ($dirty) {
    Fail 'Tracked application files have local changes. Update stopped to protect those changes.'
    Write-Host $dirty
    exit 1
}

$previous = (git -C $Root rev-parse HEAD).Trim()
$previousBranch = (git -C $Root rev-parse --abbrev-ref HEAD).Trim()
$targetBranch = if ($Branch) { $Branch.Trim() } else { $previousBranch }
Write-MorphorumDetail 'Current branch' $previousBranch
Write-MorphorumDetail 'Target branch' $targetBranch
Write-MorphorumDetail 'Current commit' $previous.Substring(0, [Math]::Min(12, $previous.Length))

if (-not $targetBranch -or $targetBranch -eq 'HEAD') {
    Fail 'Detached Git HEAD. Specify a branch, for example: update.bat main'
    exit 1
}

if ($Branch) {
    Write-MorphorumSection 'REMOTE BRANCH'
    Step "Fetching branch information from origin..."
    git -C $Root fetch origin --prune
    if ($LASTEXITCODE -ne 0) {
        Fail 'Could not fetch branches from GitHub. Check the connection and retry.'
        exit $LASTEXITCODE
    }

    git -C $Root show-ref --verify --quiet "refs/remotes/origin/$targetBranch"
    if ($LASTEXITCODE -ne 0) {
        Fail "Branch 'origin/$targetBranch' was not found. Confirm the branch name."
        exit 1
    }
}

Write-MorphorumSection 'RECOVERY BACKUP'
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
    Write-MorphorumSection 'SOURCE UPDATE'
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

    Write-MorphorumSection 'RUNTIME + DEPENDENCIES'
    & (Join-Path $Root 'scripts\install_windows.ps1') -Update
    if ($LASTEXITCODE -ne 0) { throw "installer returned exit code $LASTEXITCODE" }
    Write-MorphorumSection 'UPDATE COMPLETE'
    Okay "Morphorum successfully updated on branch '$targetBranch'."
    Write-MorphorumNext 'Launch' "$Root\run.bat"
    Write-MorphorumNext 'LAN launch' "$Root\run-lan.bat"
    Write-MorphorumDetail 'Backup' $backup
}
catch {
    Write-MorphorumSection 'UPDATE FAILED / RECOVERY'
    Fail "Update failed: $($_.Exception.Message)"
    Warn "Rolling source tree back to branch '$previousBranch' at $previous and restoring the previous runtime dependencies..."

    if ($previousBranch -and $previousBranch -ne 'HEAD') {
        git -C $Root switch $previousBranch
        if ($LASTEXITCODE -ne 0) {
            Fail 'Automatic branch rollback failed. Resolve the Git error, then run repair.bat.'
            exit 1
        }
    }
    else {
        git -C $Root checkout --detach $previous
        if ($LASTEXITCODE -ne 0) {
            Fail 'Automatic detached-HEAD rollback failed. Resolve the Git error, then run repair.bat.'
            exit 1
        }
    }

    git -C $Root reset --hard $previous
    if ($LASTEXITCODE -ne 0) {
        Fail 'Automatic source rollback failed. Run repair.bat after resolving the Git error.'
        exit 1
    }
    & (Join-Path $Root 'scripts\install_windows.ps1') -Repair
    Fail 'Update rolled back. Your previous Morphorum source version was restored.'
    Write-MorphorumDetail 'Backup' $backup
    exit 1
}
