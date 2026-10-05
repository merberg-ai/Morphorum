#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/merberg-ai/Morphorum.git"
INSTALL_ROOT="${1:-${MORPHORUM_HOME:-$HOME/Morphorum}}"

if [[ "$INSTALL_ROOT" == "~" ]]; then
  INSTALL_ROOT="$HOME"
elif [[ "$INSTALL_ROOT" == ~/* ]]; then
  INSTALL_ROOT="$HOME/${INSTALL_ROOT#~/}"
fi

if [[ "$INSTALL_ROOT" != /* ]]; then
  INSTALL_ROOT="$(pwd)/$INSTALL_ROOT"
fi

echo
echo "Morphorum bootstrap"
echo "==================="
echo "Install directory: $INSTALL_ROOT"

if ! command -v git >/dev/null 2>&1; then
  echo "Git is required. Install git with your distribution package manager, then rerun this command." >&2
  exit 1
fi

INSTALL_PARENT="$(dirname "$INSTALL_ROOT")"
mkdir -p "$INSTALL_PARENT"

if [[ -d "$INSTALL_ROOT/.git" ]]; then
  echo "Existing Morphorum checkout found; updating..."
  git -C "$INSTALL_ROOT" pull --ff-only
elif [[ -d "$INSTALL_ROOT" ]] && [[ -n "$(ls -A "$INSTALL_ROOT" 2>/dev/null || true)" ]]; then
  echo "Install directory exists and is not a Morphorum git checkout: $INSTALL_ROOT" >&2
  exit 1
else
  git clone "$REPO" "$INSTALL_ROOT"
fi

chmod +x "$INSTALL_ROOT/install.sh" "$INSTALL_ROOT/run.sh" "$INSTALL_ROOT/update.sh" "$INSTALL_ROOT/repair.sh" 2>/dev/null || true
"$INSTALL_ROOT/install.sh"

echo
echo "Morphorum is installed at $INSTALL_ROOT"
echo "Start it with: $INSTALL_ROOT/run.sh"
