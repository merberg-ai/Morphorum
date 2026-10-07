#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
HOST="${MORPHORUM_HOST_OVERRIDE:-127.0.0.1}"
PORT="${MORPHORUM_PORT_OVERRIDE:-7865}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Morphorum is not installed yet. Run ./install.sh first." >&2
  exit 1
fi

printf 'Morphorum starting at http://%s:%s\n' "$HOST" "$PORT"
if command -v git >/dev/null 2>&1; then
  BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ -n "$BRANCH" ]] && printf 'Git branch: %s\n' "$BRANCH"
fi
exec "$PYTHON" -m morphorum serve --host "$HOST" --port "$PORT"
