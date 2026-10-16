"""MS6.3: read-only download reporting, restart recovery and no-network regressions."""
from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

import morphorum.managed_models as mm

app_module = importlib.import_module("morphorum.app")


@pytest.fixture
def model_root(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "managed_model_location", lambda family: tmp_path)
    monkeypatch.setattr(mm, "remove_managed_model", lambda index_id: None)
    monkeypatch.setattr(mm.ManagedModelManager, "_migrate_legacy_completion",
                        classmethod(lambda cls, entry, path: False))
    return tmp_path


def test_status_without_model_is_read_only_and_reports_destination_free_bytes(model_root):
    manager = mm.ManagedModelManager()
    dest = model_root / "Z-Image-Turbo"
    assert not dest.exists()
    result = manager.status("zimage-turbo")
    assert result["status"] == "not_installed"
    assert result["installed"] is False
    assert result["available_bytes"] is not None
    assert result["estimated_remaining_bytes"] == result["advertised_size_bytes"]
    assert result["required_free_bytes"] > result["estimated_remaining_bytes"]
    assert not dest.exists(), "GET must not create model directories"
    assert not (dest / mm._DOWNLOAD_MARKER).exists()


def test_interrupted_download_is_visible_after_restart_without_auto_resuming(model_root):
    dest = model_root / "Z-Image-Turbo"
    dest.mkdir()
    (dest / "chunk.safetensors").write_bytes(b"x" * 700)
    (dest / mm._DOWNLOAD_MARKER).write_text(json.dumps({
        "status": "downloading",
        "model_id": "zimage-turbo",
        "repo_id": mm.MANAGED_MODEL_CATALOG["zimage-turbo"]["repo_id"],
        "expected_bytes": 1400,
    }))
    before = (dest / mm._DOWNLOAD_MARKER).read_bytes()
    first = mm.ManagedModelManager().status("zimage-turbo")
    second = mm.ManagedModelManager().status("zimage-turbo")
    for state in (first, second):
        assert state["status"] == "interrupted"
        assert not state["installed"]
        assert state["resumable"]
        assert state["downloaded_bytes"] >= 700
        assert state["progress_percent"] < 100
        assert state["expected_bytes"] == 1400
    assert (dest / mm._DOWNLOAD_MARKER).read_bytes() == before


def test_incomplete_package_is_not_100_percent_even_if_oversized(model_root):
    dest = model_root / "Z-Image-Turbo"
    dest.mkdir()
    (dest / "chunk.safetensors").write_bytes(b"z" * 400)
    (dest / mm._DOWNLOAD_MARKER).write_text(json.dumps({
        "status": "downloading",
        "model_id": "zimage-turbo",
        "repo_id": mm.MANAGED_MODEL_CATALOG["zimage-turbo"]["repo_id"],
        "expected_bytes": 100,
    }))
    state = mm.ManagedModelManager().status("zimage-turbo")
    assert state["installed"] is False
    assert state["progress_percent"] == 99.9


def test_failed_snapshot_is_saved_and_can_be_diagnosed_after_restart(model_root, monkeypatch):
    from huggingface_hub import snapshot_download

    def network_disabled(*args, **kwargs):
        raise RuntimeError("simulated network interruption")

    monkeypatch.setattr("huggingface_hub.snapshot_download", network_disabled)
    manager = mm.ManagedModelManager()
    manager._states["zimage-turbo"] = mm.DownloadState(model_id="zimage-turbo")
    manager._download_worker("zimage-turbo")
    state = mm.ManagedModelManager().status("zimage-turbo")
    assert state["status"] == "failed"
    assert state["resumable"]
    assert state["installed"] is False
    assert "simulated network interruption" in state["error"]
    assert (model_root / "Z-Image-Turbo" / mm._DOWNLOAD_MARKER).is_file()


def test_existing_status_endpoint_never_calls_download(model_root, monkeypatch):
    manager = mm.ManagedModelManager()
    monkeypatch.setattr(app_module, "managed_model_manager", manager)
    calls = []
    monkeypatch.setattr(manager, "start_download", lambda model_id: calls.append(model_id))
    with TestClient(app_module.app) as client:
        response = client.get("/api/managed-models/zimage-turbo")
        assert response.status_code == 200
        data = response.json()
        assert data["installed"] is False
        assert data["available_bytes"] is not None
        assert client.get("/api/managed-models").status_code == 200
    assert not calls
