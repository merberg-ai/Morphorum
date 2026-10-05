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

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "A system package needs to be installed, but sudo is unavailable." >&2
    return 1
  fi
}

install_git() {
  echo "Git was not found; attempting to install it..."
  if command -v apt-get >/dev/null 2>&1; then
    run_privileged apt-get update
    run_privileged apt-get install -y git
  elif command -v dnf >/dev/null 2>&1; then
    run_privileged dnf install -y git
  elif command -v pacman >/dev/null 2>&1; then
    run_privileged pacman -Sy --needed --noconfirm git
  elif command -v zypper >/dev/null 2>&1; then
    run_privileged zypper --non-interactive install git
  else
    echo "No supported package manager was found. Install Git manually, then rerun this command." >&2
    return 1
  fi
}

if ! command -v git >/dev/null 2>&1; then
  install_git
fi
command -v git >/dev/null 2>&1 || { echo "Git is still unavailable after the install attempt." >&2; exit 1; }

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

chmod +x "$INSTALL_ROOT"/*.sh "$INSTALL_ROOT/scripts"/*.sh 2>/dev/null || true
"$INSTALL_ROOT/install.sh"

echo
echo "Morphorum is installed at $INSTALL_ROOT"
echo "Local: $INSTALL_ROOT/run.sh"
echo "LAN:   $INSTALL_ROOT/run-lan.sh"
