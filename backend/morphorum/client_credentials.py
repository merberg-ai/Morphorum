"""DB2.2 local-only client credential administration.

No LAN pairing endpoint exists. Administrators issue high-entropy client tokens
on the backend host and provision them out-of-band over a trusted channel.
Only SHA-256 digests of tokens are stored in the server credential registry.
Revocation is observed immediately because authentication reloads the registry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .paths import DATA_DIR, ensure_runtime_dirs

CLIENTS_PATH = DATA_DIR / "backend-client-credentials.json"
_LOCK = threading.RLock()
_TOKEN_PATTERN = re.compile(r"^mcp1_([0-9a-f]{16})_([A-Za-z0-9_-]{40,128})$")
_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_MAX_CLIENTS = 64


class ClientCredentialError(RuntimeError):
    pass


def _timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _read_registry() -> dict:
    path = Path(CLIENTS_PATH)
    if not path.exists():
        return {"schema_version": 1, "clients": []}
    if not path.is_file() or path.is_symlink():
        raise ClientCredentialError("Client credential registry must be a regular file.")
    if os.name != "nt" and (stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ClientCredentialError("Client credential registry file permissions are too broad.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClientCredentialError("Client credential registry is unreadable.") from exc
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("clients"), list)
            or len(data["clients"]) > _MAX_CLIENTS):
        raise ClientCredentialError("Client credential registry schema is invalid.")
    for record in data["clients"]:
        if (not isinstance(record, dict)
                or not _ID_PATTERN.fullmatch(str(record.get("id", "")))
                or not isinstance(record.get("name"), str)
                or not isinstance(record.get("digest"), str)
                or not re.fullmatch("[0-9a-f]{64}", record["digest"])
                or not isinstance(record.get("expires_at"), (int, float))
                or not isinstance(record.get("revoked"), bool)):
            raise ClientCredentialError("Client credential registry contains an invalid record.")
    return data


def _write_registry(data: dict) -> None:
    ensure_runtime_dirs()
    target = Path(CLIENTS_PATH)
    if target.is_symlink():
        raise ClientCredentialError("Client credential registry must not be a symlink.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def issue_client_token(name: str, *, lifetime_days: int = 90) -> tuple[str, dict]:
    """Issue a token once; never return it from list endpoints or persist it raw."""
    label = str(name).strip()
    if not label or len(label) > 80 or any(ord(c) < 32 for c in label):
        raise ClientCredentialError("Client name must be 1-80 printable characters.")
    if not isinstance(lifetime_days, int) or not 1 <= lifetime_days <= 365:
        raise ClientCredentialError("Client lifetime must be between 1 and 365 days.")
    with _LOCK:
        data = _read_registry()
        if len(data["clients"]) >= _MAX_CLIENTS:
            raise ClientCredentialError("Client credential limit reached.")
        identifier = secrets.token_hex(8)
        while any(item["id"] == identifier for item in data["clients"]):
            identifier = secrets.token_hex(8)
        token = f"mcp1_{identifier}_{secrets.token_urlsafe(48)}"
        now = time.time()
        record = {
            "id": identifier,
            "name": label,
            "digest": hashlib.sha256(token.encode("ascii")).hexdigest(),
            "created_at": _timestamp(now),
            "expires_at": int(now + lifetime_days * 86400),
            "revoked": False,
        }
        data["clients"].append(record)
        _write_registry(data)
        return token, _public_record(record)


def _public_record(record: dict) -> dict:
    return {key: record[key] for key in ("id", "name", "created_at", "expires_at", "revoked")}


def list_clients() -> list[dict]:
    with _LOCK:
        return [_public_record(record) for record in _read_registry()["clients"]]


def revoke_client(identifier: str) -> dict:
    with _LOCK:
        data = _read_registry()
        for record in data["clients"]:
            if hmac.compare_digest(str(record["id"]), str(identifier)):
                if not record["revoked"]:
                    record["revoked"] = True
                    _write_registry(data)
                return _public_record(record)
        raise ClientCredentialError("Client identifier not found.")


def authorized_client_token(token: str) -> bool:
    match = _TOKEN_PATTERN.fullmatch(token)
    if not match:
        return False
    try:
        with _LOCK:
            clients = _read_registry()["clients"]
    except ClientCredentialError:
        # Fail closed on a corrupted or insecure registry.
        return False
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    now = time.time()
    authorized = False
    for record in clients:
        # Avoid an early digest-match return.
        equal = (hmac.compare_digest(record["id"], match.group(1))
                 and hmac.compare_digest(record["digest"], digest))
        authorized = authorized or (equal and not record["revoked"]
                                     and record["expires_at"] > now)
    return authorized


def write_issued_token(path: Path, token: str) -> None:
    """Safely write the *only* issued secret copy to a new operator-owned file."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as output:
        output.write(token + "\n")
        output.flush()
        os.fsync(output.fileno())
