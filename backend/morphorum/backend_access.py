"""Authentication for Morphorum's opt-in API-only server.

The standard browser application does not use this mechanism. API-only mode
requires a high-entropy bearer token even when listening on loopback.
"""
from __future__ import annotations

import hmac
import os
import secrets
import stat
from functools import lru_cache
from pathlib import Path

from .client_credentials import authorized_client_token
from .paths import DATA_DIR, ensure_runtime_dirs

TOKEN_PATH = DATA_DIR / "backend-access-token"


def backend_token_file() -> Path:
    return TOKEN_PATH


@lru_cache(maxsize=1)
def resolve_backend_token() -> str:
    supplied = os.getenv("MORPHORUM_BACKEND_TOKEN", "").strip()
    if supplied:
        if len(supplied) < 32:
            raise RuntimeError("MORPHORUM_BACKEND_TOKEN must be at least 32 characters.")
        return supplied

    ensure_runtime_dirs()
    try:
        fd = os.open(str(TOKEN_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        try:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(secrets.token_urlsafe(48) + "\n")
        except BaseException:
            TOKEN_PATH.unlink(missing_ok=True)
            raise

    if not TOKEN_PATH.is_file():
        raise RuntimeError("Backend access token file was not created.")
    if os.name != "nt" and stat.S_IMODE(TOKEN_PATH.stat().st_mode) & 0o077:
        raise RuntimeError(
            f"Backend token permissions are too broad: {TOKEN_PATH}. "
            "Restrict permissions with chmod 600."
        )
    token = TOKEN_PATH.read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise RuntimeError(f"Backend access token in {TOKEN_PATH} is too short.")
    return token


def authorized_backend_request(header: str | None) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    offered = header.removeprefix("Bearer ").strip()
    return bool(offered) and (hmac.compare_digest(offered, resolve_backend_token()) or authorized_client_token(offered))
