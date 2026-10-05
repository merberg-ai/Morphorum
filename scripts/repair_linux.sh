#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Morphorum Doctor"
echo "==============="
for cmd in git ffmpeg nvidia-smi; do
  if command -v "$cmd" >/dev/null 2>&1; then echo "[OK] $cmd"; else echo "[!] $cmd not found"; fi
done
if [[ -x .venv/bin/python ]]; then
  echo "[OK] Python virtual environment"
  .venv/bin/python --version
  .venv/bin/python -c "import torch; print('PyTorch:', torch.__version__, 'CUDA:', torch.cuda.is_available())" 2>/dev/null || echo "[!] PyTorch not installed yet."
else
  echo "[!] Python virtual environment missing."
fi

echo
exec "$ROOT/scripts/install_linux.sh"
