"""PS5.2: real attached media, explicit per-request consent and vision capability gates.

Provider traffic is mocked. This does not claim a physical vision model test.
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
import morphorum.prompt_studio_vision as vision
from morphorum.app import app
from morphorum.prompt_studio_ollama import OllamaStoryError


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (33, 44, 55)).save(buffer, format="PNG")
    return buffer.getvalue()


def _project(client):
    created = client.post("/api/animation/projects", json={"name": "Vision opt-in"})
    assert created.status_code == 201, created.text
    pid = created.json()["project"]["id"]
    etag = client.get(f"/api/animation/projects/{pid}").headers["etag"]
    uploaded = client.post(
        f"/api/animation/projects/{pid}/source-image",
        content=_png(), headers={"If-Match": etag, "X-Filename": "start.png"},
    )
    assert uploaded.status_code == 201, uploaded.text
    return pid, uploaded.json()["asset"]["sha256"]


def _req(pid, digest):
    return {"project_id": pid, "source_sha256": digest,
            "endpoint": "http://127.0.0.1:11434",
            "model": "llava:latest", "consent": True}


def test_ps52_requires_exact_source_and_explicit_consent_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    async def denied(*args, **kwargs):
        pytest.fail("Ollama should not receive anything when preflight fails")
    monkeypatch.setattr(vision, "_http_json", denied)
    with TestClient(app) as client:
        pid, digest = _project(client)
        good = _req(pid, digest)
        for change in (
            {"consent": False}, {"consent": 1},
            {"source_sha256": "0" * 64},
            {"image_path": "C:/Users/test/private.png"},
            {"image_url": "http://example.com/image.png"},
            {"endpoint": "http://192.168.1.5:11434"},
            {"endpoint": "http://example.com:11434"},
            {"model": "not valid name?"},
        ):
            res = client.post("/api/prompt-studio/ollama/analyze-start-image",
                              json={**good, **change})
            assert res.status_code in (400, 409), (change, res.text)
        missing = client.post("/api/prompt-studio/ollama/analyze-start-image",
                              json={**good, "project_id": "not-here"})
        assert missing.status_code == 404


def test_ps52_model_must_advertise_vision_before_image_transfer(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    calls = []
    async def fake(endpoint, route, **kwargs):
        calls.append(route)
        return {"capabilities": ["completion", "tools"]}
    monkeypatch.setattr(vision, "_http_json", fake)
    with TestClient(app) as client:
        pid, digest = _project(client)
        result = client.post("/api/prompt-studio/ollama/analyze-start-image",
                             json=_req(pid, digest))
        assert result.status_code == 422
        assert "No image was sent" in result.text
        assert calls == ["/api/show"]


def test_ps52_consent_transmits_only_downscaled_project_image_and_never_mutates(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    calls = []
    async def fake(endpoint, route, **kwargs):
        calls.append((endpoint, route, kwargs.get("body")))
        if route == "/api/show":
            return {"capabilities": ["completion", "vision"]}
        return {"message": {"content": json.dumps({
            "description": "A small blue-gray image with a rectangular composition."
        })}}
    monkeypatch.setattr(vision, "_http_json", fake)
    with TestClient(app) as client:
        pid, digest = _project(client)
        project_before = client.get(f"/api/animation/projects/{pid}")
        result = client.post("/api/prompt-studio/ollama/analyze-start-image",
                             json=_req(pid, digest))
        assert result.status_code == 200, result.text
        assert result.json()["source_sha256"] == digest
        assert "rectangular composition" in result.json()["description"]
        assert [x[1] for x in calls] == ["/api/show", "/api/chat"]
        assert all(x[0] == "http://127.0.0.1:11434" for x in calls)
        body = calls[1][2]
        image = base64.b64decode(body["messages"][1]["images"][0])
        with Image.open(io.BytesIO(image)) as im:
            assert im.format == "JPEG"
            assert im.size == (24, 16)
        assert "images" not in str(calls[0][2])
        assert body["keep_alive"] == "0"
        assert client.get(f"/api/animation/projects/{pid}").headers["etag"] == project_before.headers["etag"]


def test_ps52_rejects_symlink_and_malformed_image_before_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    async def denied(*args, **kwargs):
        pytest.fail("No provider call allowed")
    monkeypatch.setattr(vision, "_http_json", denied)
    with TestClient(app) as client:
        pid, digest = _project(client)
        root = projects.animation_project_directory(pid)
        image = root / "assets" / "source.png"
        image.unlink()
        image.write_bytes(b"Not an image")
        from hashlib import sha256
        corrupted = sha256(b"Not an image").hexdigest()
        result = client.post("/api/prompt-studio/ollama/analyze-start-image",
                             json=_req(pid, corrupted))
        assert result.status_code == 422
        image.unlink()
        try:
            image.symlink_to(tmp_path / "outside.png")
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks unavailable on this platform")
        result = client.post("/api/prompt-studio/ollama/analyze-start-image",
                             json=_req(pid, digest))
        assert result.status_code == 409


@pytest.mark.parametrize("response", [
    {"message": {"content": "not json"}},
    {"message": {"content": '{"description":""}'}},
    {"message": {"content": '{"description":"ok","command":"run"}'}},
])
def test_ps52_rejects_invalid_model_text(tmp_path, monkeypatch, response):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    async def fake(endpoint, route, **kwargs):
        return {"capabilities": ["vision"]} if route == "/api/show" else response
    monkeypatch.setattr(vision, "_http_json", fake)
    with TestClient(app) as client:
        pid, digest = _project(client)
        result = client.post("/api/prompt-studio/ollama/analyze-start-image",
                             json=_req(pid, digest))
        assert result.status_code == 422
