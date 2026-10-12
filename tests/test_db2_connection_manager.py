"""DB2.2: revocable tokens, secure metadata, connection lifecycle (no GPU)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from morphorum import backend_access, client_credentials as cc
from morphorum.cli import command_clients


@pytest.fixture
def credential_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "CLIENTS_PATH", tmp_path / "clients.json")
    monkeypatch.setattr(backend_access, "resolve_backend_token", lambda: "legacy" * 10)
    return tmp_path


def test_per_client_token_issue_revoke_and_legacy_compat(credential_registry):
    first, info = cc.issue_client_token("Ubuntu Mini", lifetime_days=4)
    second, other = cc.issue_client_token("Desktop Studio", lifetime_days=90)
    assert first.startswith("mcp1_" + info["id"] + "_")
    assert first != second
    registry_file = credential_registry / "clients.json"
    raw = registry_file.read_text()
    assert first not in raw and second not in raw
    assert "digest" in raw
    assert first not in json.dumps(cc.list_clients())
    assert len(cc.list_clients()) == 2
    if os.name != "nt":
        assert registry_file.stat().st_mode & 0o077 == 0
    assert backend_access.authorized_backend_request(f"Bearer {first}")
    assert backend_access.authorized_backend_request(f"Bearer {second}")
    assert backend_access.authorized_backend_request("Bearer " + "legacy" * 10)
    assert not backend_access.authorized_backend_request("Bearer " + first[:-1] + "x")
    cc.revoke_client(info["id"])
    assert not backend_access.authorized_backend_request(f"Bearer {first}")
    assert backend_access.authorized_backend_request(f"Bearer {second}")
    assert backend_access.authorized_backend_request("Bearer " + "legacy" * 10)
    assert cc.list_clients()[0]["revoked"]
    assert cc.revoke_client(info["id"])["revoked"]
    with pytest.raises(cc.ClientCredentialError, match="not found"):
        cc.revoke_client("a" * 16)


def test_expired_token_and_invalid_registry_fail_closed(credential_registry, monkeypatch):
    token, _ = cc.issue_client_token("Temporary", lifetime_days=1)
    assert cc.authorized_client_token(token)
    monkeypatch.setattr(cc.time, "time", lambda: 9999999999.0)
    assert not cc.authorized_client_token(token)
    monkeypatch.undo()
    # Mutate only the real fixture registry, not any test-wide installation file.
    registry_file = credential_registry / "clients.json"
    registry_file.write_text("corrupt")
    registry_file.chmod(0o600)
    assert not cc.authorized_client_token(token)


def test_client_registry_guards_and_cli_token_file(credential_registry, tmp_path):
    with pytest.raises(cc.ClientCredentialError):
        cc.issue_client_token("", lifetime_days=90)
    with pytest.raises(cc.ClientCredentialError):
        cc.issue_client_token("a", lifetime_days=0)
    secret = tmp_path / "once.token"
    result = command_clients(SimpleNamespace(
        clients_action="issue", name="Laptop", days=30, out=str(secret)
    ))
    assert result == 0 and secret.exists()
    assert secret.read_text().strip().startswith("mcp1_")
    assert secret.read_text().strip() not in (credential_registry / "clients.json").read_text()
    if os.name != "nt":
        assert secret.stat().st_mode & 0o077 == 0
    assert command_clients(SimpleNamespace(
        clients_action="issue", name="Laptop", days=30, out=str(secret)
    )) == 2  # refuses accidental overwrite


def test_backend_only_client_credential_authentication_in_subprocess():
    code = '''
import pathlib
import tempfile
from fastapi.testclient import TestClient
from morphorum import client_credentials as creds
from morphorum.app import app
with tempfile.TemporaryDirectory() as work:
    creds.CLIENTS_PATH = pathlib.Path(work) / "clients.json"
    token, record = creds.issue_client_token("Test Client")
    legacy = "a" * 48
    with TestClient(app) as c:
        assert c.get("/api/client/capabilities").status_code == 401
        authorized = c.get("/api/client/capabilities", headers={"Authorization": "Bearer " + token})
        assert authorized.status_code == 200
        data = authorized.json()
        assert data["authentication"]["per_client_credentials"] is True
        assert data["authentication"]["per_client_pairing"] is False
        assert c.get("/api/client/capabilities", headers={"Authorization": "Bearer " + legacy}).status_code == 200
        assert c.get("/api/client/capabilities", headers={"Authorization": "Bearer bad"}).status_code == 401
        assert c.get("/api/clients").status_code == 401  # no management endpoint
        creds.revoke_client(record["id"])
        assert c.get("/api/health", headers={"Authorization": "Bearer " + token}).status_code == 401
        assert c.get("/api/health", headers={"Authorization": "Bearer " + legacy}).status_code == 200
'''
    env = os.environ.copy()
    env["MORPHORUM_BACKEND_ONLY"] = "1"
    env["MORPHORUM_BACKEND_TOKEN"] = "a" * 48
    run = subprocess.run(
        [sys.executable, "-c", code], env=env,
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.fixture
def conn_module(monkeypatch):
    from importlib import import_module
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return import_module("morphorum_connections")


def test_profiles_are_secret_free_and_pinned(conn_module, tmp_path):
    profiles = conn_module.ProfileStore(tmp_path / "connections.json")
    profiles.add("omen", "http://192.168.1.24:7866", "Windows GPU")
    record = profiles.get("omen")
    assert record["instance_id"] is None
    assert record["url"] == "http://192.168.1.24:7866"
    raw = profiles.path.read_text()
    assert "Bearer" not in raw and "token" not in raw.lower()
    if os.name != "nt":
        assert profiles.path.stat().st_mode & 0o077 == 0
    with pytest.raises(conn_module.ProfileError, match="not pinned"):
        profiles.update_identity("omen", instance_id="a" * 32, boot_id="b" * 32)
    assert profiles.update_identity("omen", instance_id="a" * 32, boot_id="b" * 32,
                                    trust_first=True) == "connected"
    assert profiles.update_identity("omen", instance_id="a" * 32, boot_id="c" * 32) == "restarted"
    with pytest.raises(conn_module.ProfileError, match="INSTANCE CHANGED"):
        profiles.update_identity("omen", instance_id="d" * 32, boot_id="e" * 32)
    assert profiles.get("omen")["instance_id"] == "a" * 32
    assert profiles.update_identity("omen", instance_id="d" * 32, boot_id="e" * 32,
                                    replace_identity=True) == "restarted"
    profiles.remove("omen")
    assert not profiles.load()["profiles"]


def test_profiles_reject_host_credentials_and_unsafe_metadata(conn_module, tmp_path):
    profiles = conn_module.ProfileStore(tmp_path / "connections.json")
    for url in ("http://user:password@example.com:7866", "https://example.com/a",
                "ftp://example.com", "http://example.com/#token", "http://example.com:bad"):
        with pytest.raises(conn_module.ProfileError):
            profiles.add("bad", url)
    profiles.add("good", "http://localhost:7866")
    with pytest.raises(conn_module.ProfileError, match="already exists"):
        profiles.add("good", "http://localhost:7866")
    data = profiles.load()
    data["profiles"]["good"]["token"] = "secret"
    profiles.save(data)
    with pytest.raises(conn_module.ProfileError, match="credentials"):
        profiles.load()


def test_connection_manager_recovery_no_silent_repin(conn_module, tmp_path):
    store = conn_module.ProfileStore(tmp_path / "connections.json")
    store.add("omen", "http://192.168.1.24:7866")
    current = ["a" * 32, "b" * 32]
    outcomes = [ConnectionError("link down"), None]

    class Fake:
        def handshake(self):
            item = outcomes.pop(0) if outcomes else None
            if item:
                raise item
            return {"instance_id": current[0], "boot_id": current[1],
                    "mode": "backend-only", "api_contract_version": 1}

    manager = conn_module.ConnectionManager(store, lambda url, token: Fake(), sleeper=lambda _: None)
    result = manager.connect("omen", "a-secret", attempts=2, trust_first=True)
    assert result["state"] == "connected"
    assert result["attempts"] == 2
    assert result["insecure_lan_http"]
    assert result["process_ownership"] == "attached_remote"
    current[1] = "c" * 32
    assert manager.connect("omen", "a-secret")["boot"] == "restarted"
    current[0] = "d" * 32
    with pytest.raises(conn_module.ProfileError, match="INSTANCE CHANGED"):
        manager.connect("omen", "a-secret")
    assert manager.state == "identity_mismatch"


def test_connection_manager_unauthorized_is_not_retried(conn_module, tmp_path):
    store = conn_module.ProfileStore(tmp_path / "connections.json")
    store.add("omen", "http://127.0.0.1:7866")
    calls = []

    class AuthError(RuntimeError):
        status = 401

    class Fake:
        def handshake(self):
            calls.append("try")
            raise AuthError("No access")
    manager = conn_module.ConnectionManager(store, lambda url, token: Fake(), sleeper=lambda _: None)
    with pytest.raises(conn_module.ProfileError, match="rejected"):
        manager.connect("omen", "invalid", attempts=5)
    assert manager.state == "unauthorized"
    assert len(calls) == 1
