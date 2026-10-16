"""P4.4.4 FastAPI FFmpeg status/install lifecycle, no download or GPU."""
from __future__ import annotations

from fastapi.testclient import TestClient

import morphorum.app as app_module
from morphorum.app import app
from morphorum.managed_ffmpeg import ManagedFFmpegError


def test_managed_api_status_and_explicit_install_cancel(monkeypatch):
    manager = app_module.managed_ffmpeg_manager
    monkeypatch.setattr(app_module, "_ffmpeg_binary_busy", lambda: False)
    monkeypatch.setattr(manager, "status", lambda: {
        "supported": True, "installed": False, "job": None,
    })
    accepted = []
    def start(**kwargs):
        accepted.append(kwargs["busy_check"])
        return {"id": "test-install", "status": "checking"}
    monkeypatch.setattr(manager, "start", start)
    monkeypatch.setattr(manager, "cancel",
                        lambda: {"id": "test-install", "status": "downloading"})
    with TestClient(app) as client:
        status = client.get("/api/tools/ffmpeg/managed")
        assert status.status_code == 200
        assert status.json()["supported"]
        assert client.get("/api/tools/ffmpeg/managed/install").status_code == 405
        request = client.post("/api/tools/ffmpeg/managed/install")
        assert request.status_code == 202, request.text
        assert request.json()["status"] == "checking"
        assert len(accepted) == 1 and callable(accepted[0])
        cancellation = client.post("/api/tools/ffmpeg/managed/cancel")
        assert cancellation.status_code == 200
        assert cancellation.json()["status"] == "downloading"


def test_managed_api_blocks_install_or_remove_during_video_jobs(monkeypatch):
    manager = app_module.managed_ffmpeg_manager
    monkeypatch.setattr(app_module, "_ffmpeg_binary_busy", lambda: True)
    calls = []
    monkeypatch.setattr(manager, "start", lambda **_kw: calls.append("install"))
    monkeypatch.setattr(manager, "remove", lambda: calls.append("remove"))
    with TestClient(app) as client:
        install = client.post("/api/tools/ffmpeg/managed/install")
        deletion = client.delete("/api/tools/ffmpeg/managed")
        assert install.status_code == 409
        assert deletion.status_code == 409
        assert "active video" in install.json()["detail"]
        assert calls == []


def test_managed_api_remove_only_via_explicit_delete(monkeypatch):
    manager = app_module.managed_ffmpeg_manager
    monkeypatch.setattr(app_module, "_ffmpeg_binary_busy", lambda: False)
    monkeypatch.setattr(manager, "remove", lambda: {"installed": False})
    with TestClient(app) as client:
        assert client.get("/api/tools/ffmpeg/managed").status_code == 200
        assert client.delete("/api/tools/ffmpeg/managed").json()["installed"] is False


def test_managed_api_propagates_guarded_action_failures(monkeypatch):
    manager = app_module.managed_ffmpeg_manager
    monkeypatch.setattr(app_module, "_ffmpeg_binary_busy", lambda: False)
    def conflict(*_args, **_kwargs):
        raise ManagedFFmpegError("Existing installation is not owned by Morphorum.")
    monkeypatch.setattr(manager, "start", conflict)
    monkeypatch.setattr(manager, "remove", conflict)
    with TestClient(app) as client:
        assert client.post("/api/tools/ffmpeg/managed/install").status_code == 409
        assert client.delete("/api/tools/ffmpeg/managed").status_code == 409


def test_proposed_path_check_does_not_save_settings(monkeypatch):
    seen = []
    monkeypatch.setattr(app_module, "ffmpeg_status", lambda settings=None: seen.append(settings) or {
        "mode": "custom", "available": False, "message": "Binary not found.",
    })
    with TestClient(app) as client:
        result = client.post("/api/tools/ffmpeg/check", json={
            "mode": "custom", "custom_path": "/missing/ffmpeg",
        })
        assert result.status_code == 200
        assert result.json()["mode"] == "custom"
        assert seen == [{"tools": {"ffmpeg": {
            "mode": "custom", "custom_path": "/missing/ffmpeg",
        }}}]
        invalid = client.post("/api/tools/ffmpeg/check", json={
            "mode": "custom", "custom_path": "",
        })
        assert invalid.status_code == 400
