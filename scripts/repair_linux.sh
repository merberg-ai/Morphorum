#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Morphorum Repair / Doctor"
echo "========================"

"$ROOT/scripts/install_linux.sh" --repair

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "[X] Python environment is still missing after repair." >&2
  exit 1
fi

echo
exec "$PYTHON" -m morphorum doctor
