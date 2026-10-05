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
exec "$PYTHON" -m morphorum serve --host "$HOST" --port "$PORT"
