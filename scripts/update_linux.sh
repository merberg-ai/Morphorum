#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ROOT/backups/update-$STAMP"
mkdir -p "$BACKUP"
printf '%s\n' "$PREVIOUS" > "$BACKUP/previous_commit.txt"

[[ -f "$ROOT/data/config.yaml" ]] && cp "$ROOT/data/config.yaml" "$BACKUP/config.yaml"
find "$ROOT/data" -maxdepth 1 -type f -name '*.db' -exec cp {} "$BACKUP/" \; 2>/dev/null || true

step "Backup created: $BACKUP"
step "Pulling Morphorum update..."
git -C "$ROOT" pull --ff-only

if "$ROOT/scripts/install_linux.sh" --update; then
  ok "Morphorum update completed successfully."
  exit 0
fi

warn "Update install/self-test failed. Rolling source tree back to $PREVIOUS..."
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
