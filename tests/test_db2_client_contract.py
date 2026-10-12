"""DB2.1 contract tests: no GPU/network sockets required."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from morphorum import client_protocol
from morphorum.app import app


@pytest.fixture
def reference_client_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "morphorum_client.py"
    spec = importlib.util.spec_from_file_location("morphorum_reference_client", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_persisted_instance_and_process_boot_id(monkeypatch, tmp_path):
    identifier = tmp_path / "backend-instance-id"
    monkeypatch.setattr(client_protocol, "BACKEND_INSTANCE_PATH", identifier)
    client_protocol.backend_instance_id.cache_clear()
    try:
        first = client_protocol.backend_instance_id()
        assert len(first) == 32
        assert identifier.read_text(encoding="ascii").strip() == first
        client_protocol.backend_instance_id.cache_clear()
        assert client_protocol.backend_instance_id() == first
        assert client_protocol.BOOT_ID != first
        if os.name != "nt":
            assert identifier.stat().st_mode & 0o077 == 0
    finally:
        client_protocol.backend_instance_id.cache_clear()


def test_instance_bad_contents_rejected(monkeypatch, tmp_path):
    identifier = tmp_path / "backend-instance-id"
    identifier.write_text("bad\n")
    identifier.chmod(0o600)
    monkeypatch.setattr(client_protocol, "BACKEND_INSTANCE_PATH", identifier)
    client_protocol.backend_instance_id.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="invalid"):
            client_protocol.backend_instance_id()
    finally:
        client_protocol.backend_instance_id.cache_clear()


def test_standard_client_capabilities_and_backward_compatible_error():
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        response = client.get("/api/client/capabilities")
        assert response.status_code == 200
        info = response.json()
        assert info["mode"] == "standard"
        assert info["api_contract_version"] == health["api_contract_version"] == 1
        assert info["client_protocol_version"] == 1
        assert len(info["instance_id"]) == len(info["boot_id"]) == 32
        assert info["authentication"]["required"] is False
        assert info["features"]["animation_render"]
        assert info["features"]["animation_gif_download"]
        assert info["features"]["job_events_sse"] is True
        assert info["features"]["job_events_replayable"] is False
        assert info["features"]["idempotent_submissions"] is True
        assert info["submissions"]["idempotency_header"] == "Idempotency-Key"
        assert info["features"]["soundtrack_attachment_download"] is True
        assert info["features"]["project_asset_listing"] is True
        assert info["features"]["conditional_project_saves"] is True
        assert info["transfers"]["motion_lab_audio"]["max_bytes"] == 20 * 1024 * 1024
        assert info["transfers"]["soundtrack_attachment"]["max_bytes"] == 40 * 1024 * 1024
        assert info["transfers"]["soundtrack_attachment"]["download"].endswith("/soundtrack/file")
        assert info["features"]["video_export"] == info["video"]["available"]
        invalid = client.post("/api/animation/renders", json={"project_id": "fake"})
        assert invalid.status_code == 400
        error = invalid.json()
        assert error["detail"] == "Animation project payload is required."
        assert error["error"]["code"] == "INVALID_REQUEST"
        assert error["error"]["message"] == error["detail"]
        assert error["error"]["request_id"] == invalid.headers["x-request-id"]
        assert len(error["error"]["request_id"]) == 24
        bad_query = client.get("/api/models?limit=abc")
        assert bad_query.status_code == 422
        assert isinstance(bad_query.json()["detail"], list)
        assert bad_query.json()["error"]["code"] == "VALIDATION_ERROR"
        missing = client.get("/api/does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_backend_only_capabilities_and_auth_error_are_protected():
    code = """
from fastapi.testclient import TestClient
from morphorum.app import app
with TestClient(app) as c:
    for path in ("/api/health", "/api/client/capabilities"):
        unauth = c.get(path)
        assert unauth.status_code == 401
        assert unauth.json()["detail"] == "Backend API authentication required."
        assert unauth.json()["error"]["code"] == "AUTH_REQUIRED"
        assert unauth.headers["www-authenticate"] == "Bearer"
    header = {"Authorization": "Bearer " + "x" * 48}
    info = c.get("/api/client/capabilities", headers=header)
    assert info.status_code == 200
    assert info.json()["mode"] == "backend-only"
    assert info.json()["authentication"]["required"] is True
    assert info.json()["authentication"]["per_client_pairing"] is False
    assert len(info.json()["boot_id"]) == 32
    forbidden = c.get("/api/client/capabilities", headers={**header, "Origin": "https://evil.example"})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "BROWSER_ORIGIN_FORBIDDEN"
    assert c.get("/").status_code == 404
"""
    env = os.environ.copy()
    env["MORPHORUM_BACKEND_ONLY"] = "1"
    env["MORPHORUM_BACKEND_TOKEN"] = "x" * 48
    completed = subprocess.run(
        [sys.executable, "-c", code], env=env,
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_reference_client_safety_and_no_external_urls(reference_client_module):
    mod = reference_client_module
    for url in ("ftp://example.com", "http://user:pass@127.0.0.1:7866",
                "http://127.0.0.1:7866/project", "https://example.test/?token=secret"):
        with pytest.raises(mod.ClientError):
            mod.MorphorumClient(url, "secret")
    cli = mod.MorphorumClient("http://127.0.0.1:7866", "test-token")
    for path in ("https://attacker.test/api/health", "//attacker.test/api/health",
                 "/not-api", "/api/../bad#fragment"):
        with pytest.raises(mod.ClientError):
            cli.request("GET", path)
    with pytest.raises(mod.ClientError):
        mod.MorphorumClient("http://127.0.0.1:7866", "")


def test_reference_client_model_and_render_payload(reference_client_module):
    mod = reference_client_module
    requests = []

    class FakeResponse:
        headers = {}
        def __init__(self, value):
            self.value = json.dumps(value).encode()
        def __enter__(self):
            return self
        def __exit__(self, *unused):
            return False
        def read(self, size=-1):
            return self.value

    responses = {
        "/api/health": {"api_contract_version": 1},
        "/api/client/capabilities": {"api_contract_version": 1},
        "/api/models?family=sdxl&kind=checkpoints&limit=500": {
            "models": [{"id": "real-index-id", "name": "artUniverse_sdxlV60_874843",
                        "filename": "artUniverse_sdxlV60_874843.safetensors"}]},
        "/api/animation/projects/test-abc": {"project": {
            "id": "test-abc", "name": "Camera Test", "animation": {"max_frames": 24},
        }},
        "/api/animation/renders": {"id": "anim-test", "status": "queued"},
        "/api/generation/jobs": {"id": "img-test", "status": "queued"},
    }

    class FakeOpener:
        def open(self, request, timeout):
            path = request.full_url.removeprefix("http://127.0.0.1:7866")
            requests.append((request.get_method(), path, request.data,
                             request.get_header("Authorization")))
            return FakeResponse(responses[path])

    cli = mod.MorphorumClient("http://127.0.0.1:7866", "redacted-secret")
    cli._opener = FakeOpener()
    assert cli.handshake()["api_contract_version"] == 1
    model = cli.resolve_model("artUniverse_sdxlV60_874843")
    assert model["id"] == "real-index-id"
    started = cli.render("test-abc")
    assert started["id"] == "anim-test"
    body = json.loads(requests[-1][2])
    assert list(body) == ["project"]
    assert body["project"]["id"] == "test-abc"
    image = cli.generate(model["id"], "haunted CRT")
    assert image["id"] == "img-test"
    body = json.loads(requests[-1][2])
    assert body["model_id"] == "real-index-id"
    assert body["guidance_scale"] == 6.5
    assert body["images"] == 1
    assert "count" not in body
    assert all(auth == "Bearer redacted-secret" for _, _, _, auth in requests)


def test_reference_client_rejects_incompatible_contract(reference_client_module):
    mod = reference_client_module
    class FakeResponse:
        headers = {}
        def __enter__(self):
            return self
        def __exit__(self, *unused):
            pass
        def read(self, size=-1):
            return b'{"api_contract_version": 999}'
    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse()
    cli = mod.MorphorumClient("http://localhost:7866", "secret")
    cli._opener = FakeOpener()
    with pytest.raises(mod.ClientError, match="Incompatible"):
        cli.handshake()
