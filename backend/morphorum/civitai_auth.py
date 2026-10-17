"""Host-only Civitai credentials. Never return token contents to browser clients."""
import os
import re
import tempfile
from pathlib import Path
from .paths import DATA_DIR, ensure_runtime_dirs

SECRET_PATH = DATA_DIR / ".civitai-token"

def get_token():
    env = os.environ.get("CIVITAI_API_TOKEN", "").strip()
    if env:
        return env
    try:
        return SECRET_PATH.read_text(encoding="utf-8").strip() if SECRET_PATH.is_file() else ""
    except OSError:
        return ""

def token_status():
    return {"configured": bool(get_token()), "source": "environment" if os.environ.get("CIVITAI_API_TOKEN", "").strip() else "saved" if SECRET_PATH.is_file() else "none"}

def store_token(token):
    token = str(token or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{12,512}", token):
        raise ValueError("Invalid API key format.")
    ensure_runtime_dirs()
    fd, name = tempfile.mkstemp(prefix=".civitai-key-", dir=str(DATA_DIR))
    try:
        try:
            os.fchmod(fd, 0o600)
        except AttributeError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(token)
        os.replace(name, SECRET_PATH)
    finally:
        Path(name).unlink(missing_ok=True)
    return token_status()

def clear_token():
    SECRET_PATH.unlink(missing_ok=True)
    return token_status()
