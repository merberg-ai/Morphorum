#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Morphorum environment is not installed. Run ./install.sh first." >&2
  exit 1
fi

if [[ -f app/main.py ]]; then
  export MORPHORUM_HOST_OVERRIDE="${MORPHORUM_HOST_OVERRIDE:-127.0.0.1}"
  exec .venv/bin/python -m app.main
fi

echo "Morphorum application server has not landed yet; this repository currently contains the project foundation." >&2
echo "See docs/ROADMAP.md for implementation milestones." >&2
exit 2
