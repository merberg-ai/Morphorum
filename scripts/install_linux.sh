#!/usr/bin/env bash
set -euo pipefail

MODE="install"
SKIP_SELF_TEST=0
for arg in "$@"; do
  case "$arg" in
    --repair) MODE="repair" ;;
    --update) MODE="update" ;;
    --skip-self-test) SKIP_SELF_TEST=1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step(){ printf '[Morphorum] %s\n' "$1"; }
ok(){ printf '[OK] %s\n' "$1"; }
warn(){ printf '[!] %s\n' "$1"; }
fail(){ printf '[X] %s\n' "$1" >&2; }

RUNTIME_DIR="$ROOT/.runtime"
UV_DIR="$RUNTIME_DIR/uv"
UV_BIN="$UV_DIR/uv"
PYTHON_DIR="$RUNTIME_DIR/python"
UV_CACHE="$RUNTIME_DIR/uv-cache"
VENV_PYTHON="$ROOT/.venv/bin/python"

export UV_INSTALL_DIR="$UV_DIR"
export UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_DIR="$PYTHON_DIR"
export UV_CACHE_DIR="$UV_CACHE"
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"

mkdir -p "$UV_DIR" "$PYTHON_DIR" "$UV_CACHE" \
  "$ROOT/data" "$ROOT/projects" "$ROOT/outputs" "$ROOT/logs" \
  "$ROOT/cache" "$ROOT/backups"

LOG="$ROOT/logs/$MODE.log"
exec > >(tee -a "$LOG") 2>&1

trap 'fail "Installer stopped at line $LINENO. See $LOG"' ERR

step "Mode: $MODE"
step "Installation root: $ROOT"

FREE_KB="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
if [[ -n "$FREE_KB" && "$FREE_KB" =~ ^[0-9]+$ ]]; then
  if (( FREE_KB < 2097152 )); then
    fail "Less than 2 GiB free at the install location."
    exit 1
  fi
  ok "Disk space: $((FREE_KB / 1048576)) GiB free"
else
  warn "Could not determine free disk space."
fi

if ! command -v git >/dev/null 2>&1; then
  fail "Git is required. Install git with your distribution package manager and rerun the bootstrap command."
  exit 1
fi
ok "$(git --version)"

if [[ ! -x "$UV_BIN" ]]; then
  step "Installing Morphorum-owned uv runtime manager..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_DIR" UV_NO_MODIFY_PATH=1 sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_DIR" UV_NO_MODIFY_PATH=1 sh
  else
    fail "Neither curl nor wget is available, so uv cannot be downloaded."
    exit 1
  fi
fi
[[ -x "$UV_BIN" ]] || { fail "uv installer completed but $UV_BIN was not found."; exit 1; }
ok "uv: $($UV_BIN --version)"

step "Ensuring managed Python 3.12 runtime..."
"$UV_BIN" python install 3.12

if [[ ! -x "$VENV_PYTHON" ]]; then
  step "Creating Morphorum virtual environment..."
  "$UV_BIN" venv --python 3.12 .venv
fi

step "Installing/updating Morphorum Python dependencies..."
"$UV_BIN" pip install --python "$VENV_PYTHON" --upgrade --editable .
ok "Python: $($VENV_PYTHON --version)"

if [[ ! -f "$ROOT/data/config.yaml" ]]; then
  cp "$ROOT/config/default.yaml" "$ROOT/data/config.yaml"
  ok "Created user configuration: data/config.yaml"
else
  ok "Existing user configuration preserved."
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ok "FFmpeg found."
else
  warn "FFmpeg is not installed. Video encoding will require it."
  if command -v apt-get >/dev/null 2>&1; then
    warn "Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y ffmpeg"
  elif command -v dnf >/dev/null 2>&1; then
    warn "Fedora: install FFmpeg from your enabled multimedia repository (for example: sudo dnf install ffmpeg)."
  elif command -v pacman >/dev/null 2>&1; then
    warn "Arch: sudo pacman -S ffmpeg"
  fi
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_INFO="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null || true)"
  [[ -n "$GPU_INFO" ]] && ok "NVIDIA GPU: $GPU_INFO" || ok "NVIDIA driver tools detected."
else
  warn "nvidia-smi not detected. CPU/other backends may still work; NVIDIA rendering requires a supported driver."
fi

if (( SKIP_SELF_TEST == 0 )); then
  step "Running Morphorum API self-test..."
  "$VENV_PYTHON" -m morphorum self-test
  ok "API health check passed."
fi

printf '\n'
ok "Morphorum installation is ready."
printf 'Local launch:  %s/run.sh\n' "$ROOT"
printf 'Diagnostics:   %s/repair.sh\n' "$ROOT"
printf 'Log:           %s\n' "$LOG"
