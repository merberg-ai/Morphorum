"""Isolated backend-only contract tests: no server sockets or GPU needed."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from morphorum import backend_access


def test_generated_backend_token_stays_stable_and_private(monkeypatch, tmp_path):
    token_path = tmp_path / "backend-access-token"
    monkeypatch.delenv("MORPHORUM_BACKEND_TOKEN", raising=False)
    monkeypatch.setattr(backend_access, "TOKEN_PATH", token_path)
    backend_access.resolve_backend_token.cache_clear()
    try:
        first = backend_access.resolve_backend_token()
        assert len(first) >= 32
        assert token_path.read_text(encoding="ascii").strip() == first
        assert backend_access.authorized_backend_request(f"Bearer {first}")
        assert not backend_access.authorized_backend_request("Bearer wrong")
        assert not backend_access.authorized_backend_request(None)
        backend_access.resolve_backend_token.cache_clear()
        assert backend_access.resolve_backend_token() == first
        if os.name != "nt":
            assert token_path.stat().st_mode & 0o077 == 0
    finally:
        backend_access.resolve_backend_token.cache_clear()


def test_backend_rejects_short_configured_token(monkeypatch):
    monkeypatch.setenv("MORPHORUM_BACKEND_TOKEN", "too-short")
    backend_access.resolve_backend_token.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="at least 32"):
            backend_access.resolve_backend_token()
    finally:
        backend_access.resolve_backend_token.cache_clear()


def test_backend_only_app_is_api_only_and_authenticated():
    # Fresh interpreter intentionally verifies CLI-selected app import mode.
    # The standard app is covered separately by existing test_api / test_health.
    code = """
from fastapi.testclient import TestClient
from morphorum.app import app, BACKEND_ONLY
assert BACKEND_ONLY
paths = {getattr(route, "path", "") for route in app.routes}
for required in (
    "/api/health", "/api/system/telemetry", "/api/system/gpu-memory",
    "/api/generation/jobs", "/api/animation/renders",
    "/api/animation/renders/{render_id}",
    "/api/animation/renders/{project_id}/{render_id}/frames/{frame}",
    "/api/animation/renders/{project_id}/{render_id}/preview",
    "/api/animation/motion-preview", "/api/animation/resolve-frame",
    "/api/animation/projects", "/api/console/stream",
):
    assert required in paths, required
assert "/" not in paths
assert "/assets" not in paths
token = "s" * 48
headers = {"Authorization": "Bearer " + token}
with TestClient(app) as client:
    assert client.get("/").status_code == 404
    assert client.get("/assets/app.js").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/console?limit=1").status_code == 401
    assert client.get("/api/generation/jobs").status_code == 401
    assert client.post("/api/animation/renders", json={}).status_code == 401
    assert client.get("/api/health", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/api/health", headers={**headers, "Origin": "https://evil.test"}).status_code == 403
    health = client.get("/api/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["mode"] == "backend-only"
    assert health.json()["frontend_asset_version"] is None
    assert client.get("/api/models/families", headers=headers).status_code == 200
    assert client.get("/api/console?limit=1", headers=headers).status_code == 200
    assert client.get("/api/system/telemetry", headers=headers).status_code == 200
"""
    env = os.environ.copy()
    env["MORPHORUM_BACKEND_ONLY"] = "1"
    env["MORPHORUM_BACKEND_TOKEN"] = "s" * 48
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
