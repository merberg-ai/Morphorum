"""DB2.5 integration hardening. No physical GPU or network required."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from morphorum.app import app
import morphorum.animation_video as video


def _load_script(name: str):
    location = Path(__file__).resolve().parents[1] / "scripts"
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))
    spec = importlib.util.spec_from_file_location("db25_" + name, location / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_video_record_digest_written_and_preserved(tmp_path, monkeypatch):
    from test_animation_video import _render_fixture
    project_id, render_id, root = _render_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "ffmpeg_executable", lambda: "ffmpeg")
    payload = b"\x00\x00\x00\x18ftypisom" + b"fake-mp4-data"
    class Encoder:
        def __init__(self, argv, **kwargs):
            Path(argv[-1]).write_bytes(payload)
            self.stdout = iter(["frame=3\n"])
        def wait(self):
            return 0
    monkeypatch.setattr(video.subprocess, "Popen", Encoder)
    manager = video.VideoExportManager()
    started = manager.start(project_id, render_id)
    import time
    for _ in range(200):
        result = manager.get(started["id"])
        if result["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert result["status"] == "completed"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    path = manager.file(project_id, render_id, "mp4", "balanced", 12)
    assert manager.checksum(path) == result["sha256"]
    assert manager.list(project_id, render_id)[0]["sha256"] == result["sha256"]
    # Older exports missing a SHA-256 remain available with computed hash.
    manifest = video._export_record_path(path)
    saved = json.loads(manifest.read_text())
    del saved["sha256"]
    manifest.write_text(json.dumps(saved))
    assert manager.checksum(path) == hashlib.sha256(payload).hexdigest()


def test_video_binary_route_exposes_checksum_and_private_cache(monkeypatch, tmp_path):
    payload = b"\x00\x00\x00\x18ftypisom" + b"video-data"
    path = tmp_path / "old-export.mp4"
    path.write_bytes(payload)
    monkeypatch.setattr(video.video_export_manager, "file", lambda *args: path)
    monkeypatch.setattr(video.video_export_manager, "checksum",
                        lambda _: hashlib.sha256(payload).hexdigest())
    with TestClient(app) as client:
        response = client.get("/api/animation/renders/demo/anim-demo/video/mp4/compact/12")
        assert response.status_code == 200
        assert response.content == payload
        assert response.headers["x-content-sha256"] == hashlib.sha256(payload).hexdigest()
        assert response.headers["etag"] == '"' + hashlib.sha256(payload).hexdigest() + '"'
        assert response.headers["cache-control"] == "private, no-store"


def test_client_download_rejects_corrupt_mp4_and_webm_without_overwrite(tmp_path):
    script = _load_script("morphorum_client")
    client = script.MorphorumClient("http://127.0.0.1:7866", "test-token")

    class FakeResponse:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, n=-1):
            value, self.data = self.data[:n], self.data[n:]
            return value
    class FakeOpener:
        body = b"not-a-video"
        def open(self, request, timeout): return FakeResponse(self.body)
    opener = FakeOpener()
    client._opener = opener
    path = tmp_path / "safe.mp4"
    path.write_bytes(b"existing-valid-output")
    with pytest.raises(script.ClientError, match="SHA-256"):
        client.download("/api/test.mp4", path, file_type="mp4", expected_sha256="0"*64)
    assert path.read_bytes() == b"existing-valid-output"
    assert not path.with_name("safe.mp4.part").exists()
    with pytest.raises(script.ClientError, match="not an MP4"):
        client.download("/api/test.mp4", path, file_type="mp4")
    assert path.read_bytes() == b"existing-valid-output"
    path2 = tmp_path / "safe.webm"
    path2.write_bytes(b"good")
    with pytest.raises(script.ClientError, match="not a WebM"):
        client.download("/api/test.webm", path2, file_type="webm")
    assert path2.read_bytes() == b"good"
    opener.body = b"\x1a\x45\xdf\xa3" + b"webm-sample"
    out = client.download("/api/test.webm", path2, file_type="webm",
                          expected_sha256=hashlib.sha256(opener.body).hexdigest())
    assert out.read_bytes() == opener.body


def test_audio_fixture_generates_real_sound_and_idempotent_manifest(tmp_path, monkeypatch):
    fixture = _load_script("db2_video_audio_fixture")
    import morphorum.animation_projects as project_mod
    import morphorum.animation_render as render_mod
    import morphorum.imported_soundtrack as soundtrack_mod
    # Use the actual application project and render managers, with data paths
    # redirected to a private pytest directory only.
    monkeypatch.setattr(project_mod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(render_mod, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(fixture, "RECEIPT", tmp_path / "fixture.json")
    assert fixture.create() == 0
    receipt = json.loads((tmp_path / "fixture.json").read_text())
    output = render_mod._render_dir(receipt["project_id"], receipt["render_id"])
    manifest = json.loads((output / "render-manifest.json").read_text())
    assert manifest["db25_fixture"] == fixture.MARK
    assert manifest["status"] == "completed"
    assert manifest["total_frames"] == 12
    frozen = manifest["project"]["_imported_soundtrack_snapshot"]
    assert frozen["format"] == "wav"
    assert frozen["bytes"] > 100
    assert all((output / "frames" / f"frame_{i:06d}.png").is_file() for i in range(12))
    assert video._read_manifest(receipt["project_id"], receipt["render_id"])["status"] == "completed" if video._render_dir == render_mod._render_dir else True
    with pytest.raises(RuntimeError, match="already exists"):
        fixture.create()
    assert fixture.cleanup() == 0
    assert not output.exists()
    assert not fixture.RECEIPT.exists()


def test_restart_check_requires_changed_boot_and_same_instance(tmp_path):
    script = _load_script("db2_final_acceptance")
    checks = script.Checks()
    class Fake:
        base_url = "http://127.0.0.1:7866"
        def handshake(self):
            return {"instance_id": "a" * 32, "boot_id": "b" * 32}
    data = {"instance_id": "a" * 32, "boot_id": "b" * 32,
            "render_id": "render-1", "backend_url": Fake.base_url}
    boot = tmp_path / "boot.json"
    script._atomic_json(boot, data)
    args = type("Args", (), {"boot_record": boot})()
    with pytest.raises(script.Failure, match="boot ID changed"):
        script.verify_boot(Fake(), checks, args)


def test_no_gpu_idempotency_replay_uses_exact_archived_session(tmp_path):
    script = _load_script("db2_final_acceptance")
    from morphorum_recovery import SessionFile
    path = tmp_path / "session.json"
    state = {
        "schema_version": 1, "backend_url": "http://127.0.0.1:7866",
        "backend_instance_id": "a" * 32, "last_boot_id": "b" * 32,
        "render_id": "anim-prior", "project_id": "fixture-project",
        "payload": {"project": {"id": "fixture-project"}},
        "idempotency_key": "original-submission-key-123",
    }
    SessionFile(path).save(state)
    class Fake:
        base_url = "http://127.0.0.1:7866"
        def __init__(self):
            self.post_count = 0
            self.ids = ["anim-prior"]
        def handshake(self):
            return {"instance_id": "a" * 32, "boot_id": "c" * 32}
        def request(self, method, route, *, payload=None, headers=None):
            if method == "GET" and route.endswith("/renders") and "/projects/" in route:
                return {"renders": [{"id": i} for i in self.ids]}
            if method == "GET":
                return {"id": "anim-prior", "status": "completed",
                        "project_id": "fixture-project"}
            if method == "POST":
                assert headers["Idempotency-Key"] == state["idempotency_key"]
                assert payload == state["payload"]
                self.post_count += 1
                return {"id": "anim-prior", "status": "completed",
                        "idempotency_replayed": True}
            raise AssertionError(route)
    client = Fake()
    checks = script.Checks()
    args = type("Args", (), {"session": path})()
    script.lost_response(client, checks, args)
    assert checks.passed == 4
    assert client.post_count == 2
    assert client.ids == ["anim-prior"]


def test_audio_fixture_cleanup_refuses_unrecognized_receipt(tmp_path, monkeypatch):
    fixture = _load_script("db2_video_audio_fixture")
    path = tmp_path / "receipt.json"
    monkeypatch.setattr(fixture, "RECEIPT", path)
    path.write_text(json.dumps({"fixture": "not-ours", "project_id": "some-other-project"}))
    with pytest.raises(RuntimeError, match="unrecognized"):
        fixture.cleanup()
