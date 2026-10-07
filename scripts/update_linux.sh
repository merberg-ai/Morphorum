#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BRANCH="${1:-}"

step(){ printf '[Morphorum] %s\n' "$1"; }
ok(){ printf '[OK] %s\n' "$1"; }
warn(){ printf '[!] %s\n' "$1"; }
fail(){ printf '[X] %s\n' "$1" >&2; }

command -v git >/dev/null 2>&1 || { fail "Git is required to update Morphorum."; exit 1; }

DIRTY="$(git -C "$ROOT" status --porcelain --untracked-files=no)"
if [[ -n "$DIRTY" ]]; then
  fail "Tracked Morphorum files have local changes. Update aborted to avoid overwriting them."
  printf '%s\n' "$DIRTY"
  exit 1
fi

PREVIOUS="$(git -C "$ROOT" rev-parse HEAD)"
PREVIOUS_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
TARGET_BRANCH="${BRANCH:-$PREVIOUS_BRANCH}"

if [[ -z "$TARGET_BRANCH" || "$TARGET_BRANCH" == "HEAD" ]]; then
  fail "Morphorum is in detached HEAD state. Specify a branch explicitly, for example: ./update.sh main"
  exit 1
fi

if [[ -n "$BRANCH" ]]; then
  step "Fetching branch information from origin..."
  git -C "$ROOT" fetch origin --prune
  if ! git -C "$ROOT" show-ref --verify --quiet "refs/remotes/origin/$TARGET_BRANCH"; then
    fail "Remote branch 'origin/$TARGET_BRANCH' was not found."
    exit 1
  fi
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ROOT/backups/update-$STAMP"
mkdir -p "$BACKUP"
printf '%s\n' "$PREVIOUS" > "$BACKUP/previous_commit.txt"
printf '%s\n' "$PREVIOUS_BRANCH" > "$BACKUP/previous_branch.txt"

[[ -f "$ROOT/data/config.yaml" ]] && cp "$ROOT/data/config.yaml" "$BACKUP/config.yaml"
find "$ROOT/data" -maxdepth 1 -type f -name '*.db' -exec cp {} "$BACKUP/" \; 2>/dev/null || true

step "Backup created: $BACKUP"

UPDATE_ERROR=""

if [[ "$TARGET_BRANCH" != "$PREVIOUS_BRANCH" ]]; then
  step "Switching Morphorum from '$PREVIOUS_BRANCH' to '$TARGET_BRANCH'..."
  if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
    if ! git -C "$ROOT" switch "$TARGET_BRANCH"; then
      UPDATE_ERROR="git switch failed"
    fi
  else
    if ! git -C "$ROOT" switch --track -c "$TARGET_BRANCH" "origin/$TARGET_BRANCH"; then
      UPDATE_ERROR="git switch --track failed"
    fi
  fi
fi

if [[ -z "$UPDATE_ERROR" ]]; then
  step "Updating branch '$TARGET_BRANCH'..."
  if ! git -C "$ROOT" pull --ff-only origin "$TARGET_BRANCH"; then
    UPDATE_ERROR="git pull failed"
  fi
fi

if [[ -z "$UPDATE_ERROR" ]] && "$ROOT/scripts/install_linux.sh" --update; then
  ok "Morphorum update completed successfully on branch '$TARGET_BRANCH'."
  exit 0
fi

if [[ -z "$UPDATE_ERROR" ]]; then
  UPDATE_ERROR="install/self-test failed"
fi
warn "$UPDATE_ERROR. Rolling source tree back to branch '$PREVIOUS_BRANCH' at $PREVIOUS..."

if [[ "$PREVIOUS_BRANCH" != "HEAD" ]]; then
  if ! git -C "$ROOT" switch "$PREVIOUS_BRANCH"; then
    fail "Automatic branch rollback failed. Resolve the Git error, then run ./repair.sh."
    exit 1
  fi
else
  if ! git -C "$ROOT" checkout --detach "$PREVIOUS"; then
    fail "Automatic detached-HEAD rollback failed. Resolve the Git error, then run ./repair.sh."
    exit 1
  fi
fi

if ! git -C "$ROOT" reset --hard "$PREVIOUS"; then
  fail "Automatic source rollback failed. Run ./repair.sh after resolving the Git error."
  exit 1
fi

if ! "$ROOT/scripts/install_linux.sh" --repair; then
  fail "Source rollback succeeded, but restoring previous runtime dependencies failed."
  fail "Backup: $BACKUP"
  exit 1
fi

fail "The update was rolled back. Morphorum should be back on the previous version."
printf 'Backup: %s\n' "$BACKUP"
exit 1
