"""DB2.2 standalone connection profiles/lifecycle for Morphorum's native client.

Only public connection metadata is saved here. Credentials must be supplied
with a protected token file, environment, or an available OS keyring.
Instance pinning is *not* a substitute for HTTPS/VPN server authentication.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from urllib.parse import urlsplit

PROFILE_PATH = Path.home() / ".config" / "morphorum" / "connections.json"
SERVICE = "morphorum-studio-backend"
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")


class ProfileError(RuntimeError):
    pass


def validate_url(url: str) -> str:
    p = urlsplit(url)
    if (p.scheme not in {"http", "https"} or not p.hostname
            or p.username or p.password or p.path not in {"", "/"}
            or p.query or p.fragment):
        raise ProfileError("A profile URL must be an HTTP(S) origin without credentials.")
    try:
        p.port
    except ValueError as exc:
        raise ProfileError("Invalid backend port.") from exc
    return p.scheme + "://" + p.netloc


class ProfileStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else PROFILE_PATH

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "profiles": {}}
        if self.path.is_symlink() or not self.path.is_file():
            raise ProfileError("Connection profile path must be a regular file.")
        if os.name != "nt" and stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise ProfileError("Connection profiles have unsafe file permissions.")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProfileError("Connection profiles cannot be read.") from exc
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("profiles"), dict)):
            raise ProfileError("Invalid connection profiles schema.")
        for name, item in data["profiles"].items():
            if not NAME.fullmatch(name) or not isinstance(item, dict):
                raise ProfileError("Invalid stored profile name.")
            if set(item) != {"url", "instance_id", "boot_id", "label"}:
                raise ProfileError("Invalid profile fields; credentials must not be stored here.")
            validate_url(item["url"])
            for field in ("instance_id", "boot_id"):
                value = item[field]
                if value is not None and not re.fullmatch(r"[0-9a-f]{32}", str(value)):
                    raise ProfileError("Invalid backend identity field.")
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ProfileError("Refusing to overwrite a symlink.")
        temporary = self.path.with_name("." + self.path.name + "." + secrets.token_hex(8))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def add(self, name: str, url: str, label: str = "") -> dict:
        if not NAME.fullmatch(name):
            raise ProfileError("Profile name must be 1-48 letters/numbers/hyphens/underscores.")
        origin = validate_url(url)
        data = self.load()
        if name in data["profiles"]:
            raise ProfileError("Profile already exists; remove it before recreating.")
        profile = {"url": origin, "instance_id": None, "boot_id": None,
                   "label": str(label)[:80]}
        data["profiles"][name] = profile
        self.save(data)
        return profile

    def get(self, name: str) -> dict:
        data = self.load()
        if name not in data["profiles"]:
            raise ProfileError(f"Profile {name!r} is not configured.")
        return data["profiles"][name]

    def remove(self, name: str) -> None:
        data = self.load()
        if name not in data["profiles"]:
            raise ProfileError("Profile not found.")
        del data["profiles"][name]
        self.save(data)

    def update_identity(self, name: str, *, instance_id: str, boot_id: str,
                        trust_first: bool = False, replace_identity: bool = False) -> str:
        for value in (instance_id, boot_id):
            if not re.fullmatch(r"[0-9a-f]{32}", str(value)):
                raise ProfileError("Server returned invalid identity data.")
        data = self.load()
        if name not in data["profiles"]:
            raise ProfileError("Profile not found.")
        profile = data["profiles"][name]
        saved_id = profile["instance_id"]
        if saved_id is None and not trust_first:
            raise ProfileError("Backend identity not pinned; rerun connect with --trust-first.")
        if saved_id is not None and saved_id != instance_id and not replace_identity:
            raise ProfileError("Backend INSTANCE CHANGED. Refusing automatic re-pairing.")
        changed_boot = profile["boot_id"] is not None and profile["boot_id"] != boot_id
        profile["instance_id"] = instance_id
        profile["boot_id"] = boot_id
        self.save(data)
        return "restarted" if changed_boot else "connected"


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError as exc:
        raise ProfileError(
            "OS keyring support is unavailable. Install Python keyring with an "
            "OS credential provider, or use --token-file."
        ) from exc


def keyring_set(name: str, token: str) -> None:
    if not NAME.fullmatch(name) or not token.strip():
        raise ProfileError("Invalid profile or empty credential.")
    try:
        _keyring().set_password(SERVICE, name, token.strip())
    except Exception as exc:
        raise ProfileError("OS credential storage failed; credential was not saved.") from exc


def keyring_get(name: str) -> str | None:
    try:
        return _keyring().get_password(SERVICE, name)
    except Exception as exc:
        raise ProfileError("Unable to access the OS credential store.") from exc


def keyring_delete(name: str) -> None:
    try:
        _keyring().delete_password(SERVICE, name)
    except Exception as exc:
        raise ProfileError("Unable to delete the OS-stored credential.") from exc


class ConnectionManager:
    """Single-probe or bounded retry; no process control or hidden job re-submit."""

    def __init__(self, store: ProfileStore, factory, *, sleeper=time.sleep):
        self.store = store
        self.factory = factory
        self.sleep = sleeper
        self.state = "disconnected"
        self.errors = []
        self.details = None

    def connect(self, name: str, token: str, *, attempts: int = 1,
                trust_first: bool = False, replace_identity: bool = False) -> dict:
        if attempts < 1 or attempts > 10:
            raise ProfileError("Retry attempts must be between 1 and 10.")
        profile = self.store.get(name)
        self.state = "connecting"
        self.errors = []
        for index in range(attempts):
            if index:
                self.state = "reconnecting"
                self.sleep(min(8.0, 0.5 * (2 ** (index - 1))))
            try:
                client = self.factory(profile["url"], token)
                info = client.handshake()
                status = self.store.update_identity(
                    name, instance_id=info["instance_id"], boot_id=info["boot_id"],
                    trust_first=trust_first, replace_identity=replace_identity,
                )
                self.state = "connected"
                self.details = info
                return {
                    "state": self.state, "boot": status,
                    "backend_mode": info.get("mode"),
                    "url": profile["url"], "attempts": index + 1,
                    "insecure_lan_http": _is_plain_lan(profile["url"]),
                    "process_ownership": "attached_remote",
                }
            except ProfileError:
                self.state = "identity_mismatch"
                raise
            except Exception as exc:
                # ClientError from morphorum_client is imported by the caller;
                # classify using its documented status and message attributes.
                status = getattr(exc, "status", None)
                message = str(exc)
                self.errors.append(message)
                if status == 401 or status == 403:
                    self.state = "unauthorized"
                    raise ProfileError("Backend authentication was rejected.") from exc
                if "Incompatible" in message or "contract" in message.lower():
                    self.state = "incompatible"
                    raise ProfileError("Backend API is incompatible with this client.") from exc
                self.state = "offline"
                if index == attempts - 1:
                    raise ProfileError("Backend is unreachable after bounded retries.") from exc
        raise ProfileError("Unable to connect.")


def _is_plain_lan(url: str) -> bool:
    from ipaddress import ip_address
    parsed = urlsplit(url)
    if parsed.scheme != "http":
        return False
    host = parsed.hostname or ""
    if host == "localhost":
        return False
    try:
        return not ip_address(host).is_loopback
    except ValueError:
        return True
