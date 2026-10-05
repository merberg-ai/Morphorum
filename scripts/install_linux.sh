#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step(){ printf '[Morphorum] %s\n' "$1"; }
ok(){ printf '[OK] %s\n' "$1"; }
warn(){ printf '[!] %s\n' "$1"; }

step "Installation root: $ROOT"
command -v git >/dev/null 2>&1 && ok "$(git --version)" || warn "Git not found."

PYTHON=""
if command -v python3.12 >/dev/null 2>&1; then PYTHON=python3.12
elif command -v python3 >/dev/null 2>&1; then PYTHON=python3
fi

if [[ -n "$PYTHON" ]]; then
  ok "$($PYTHON --version)"
  if [[ ! -d .venv ]]; then
    step "Creating Python virtual environment..."
    "$PYTHON" -m venv .venv
  fi
  .venv/bin/python -m pip install --upgrade pip
  if [[ -f requirements.txt ]]; then
    step "Installing Python requirements..."
    .venv/bin/python -m pip install -r requirements.txt
  elif [[ -f pyproject.toml ]]; then
    step "Installing Morphorum Python package..."
    .venv/bin/python -m pip install -e .
  else
    warn "Backend dependency manifest has not landed yet; Python environment is ready."
  fi
else
  warn "Python 3 was not found. A supported Python runtime will be required once backend code lands."
fi

command -v ffmpeg >/dev/null 2>&1 && ok "FFmpeg found." || warn "FFmpeg not found yet; video encoding will require it."
command -v nvidia-smi >/dev/null 2>&1 && ok "NVIDIA driver tools detected." || warn "nvidia-smi not detected; repository setup can still continue."

mkdir -p projects renders data logs cache
ok "Runtime directories ready."

if [[ -f frontend/package.json ]]; then
  if command -v npm >/dev/null 2>&1; then
    step "Installing frontend dependencies..."
    (cd frontend && npm install && npm run build)
    ok "Frontend built."
  else
    warn "Frontend exists but npm was not found."
  fi
else
  warn "Frontend application has not landed yet; skipping frontend build."
fi

ok "Morphorum repository setup is complete."
[[ -d app ]] || warn "This is the initial project scaffold; the runnable application server is not implemented yet."
