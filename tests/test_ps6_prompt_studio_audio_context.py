"""PS6.2 fingerprint must detect changed WAV/markers/attachment/timing."""
from __future__ import annotations

import io
import wave
import pytest
from fastapi.testclient import TestClient

from morphorum import animation_projects as projects
from morphorum.audio_motion_upload import analyze_managed_wav
from morphorum.app import app
from morphorum.audio_marker_overrides import write_marker_overrides


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    return output.getvalue()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    project = projects.create_animation_project({"name": "Audio fingerprint"})
    return project["id"]


def test_ps62_verified_stamp_changes_with_saved_markers(project):
    with TestClient(app) as client:
        data = wav()
        analysis = analyze_managed_wav(project, data, fps=12, frames=120)
        sha = analysis["source_sha256"]
        path = f"/api/animation/projects/{project}/prompt-studio/audio-context/{sha}"
        first = client.get(path)
        assert first.status_code == 200, first.text
        doc = first.json()
        assert doc["source_sha256"] == sha
        assert doc["marker_mode"] == "detected"
        assert doc["markers_sha256"] is None
        assert doc["fps"] == 24
        assert client.get(path).json()["stamp"] == doc["stamp"]

        write_marker_overrides(project, {"source_sha256": sha, "duration_seconds": 1.0,
            "events": [{"id": "kick-1", "kind": "kick",
                        "time_seconds": 0.5, "enabled": True}]})
        changed = client.get(path).json()
        assert changed["marker_mode"] == "saved-edits"
        assert changed["markers_sha256"] != doc["markers_sha256"]
        assert changed["stamp"] != doc["stamp"]
        assert changed["stamp"] == client.get(path).json()["stamp"]

        write_marker_overrides(project, {"source_sha256": sha, "duration_seconds": 1.0,
            "events": [{"id": "kick-1", "kind": "kick",
                        "time_seconds": 0.75, "enabled": True}]})
        assert client.get(path).json()["stamp"] != changed["stamp"]


def test_ps62_frame_context_and_corrupt_wav_invalidate_stamp(project):
    with TestClient(app) as client:
        audio = wav()
        sha = analyze_managed_wav(project, audio, fps=12, frames=120)["source_sha256"]
        endpoint = f"/api/animation/projects/{project}/prompt-studio/audio-context/{sha}"
        original = client.get(endpoint).json()
        saved = projects.load_animation_project(project)
        saved["animation"]["fps"] = 12
        projects.save_animation_project(project, saved)
        result = client.get(endpoint)
        assert result.status_code == 200, result.text
        assert result.json()["stamp"] != original["stamp"]
        folder = projects.animation_project_directory(project) / "motion_lab_audio"
        (folder / f"{sha}.wav").write_bytes(b"corrupt")
        failed = client.get(endpoint)
        assert failed.status_code == 409
        assert "checksum" in failed.text.lower()


def test_ps62_invalid_hash_and_other_project_cannot_read_audio(project):
    with TestClient(app) as client:
        bad = client.get(f"/api/animation/projects/{project}/prompt-studio/audio-context/not-a-hash")
        assert bad.status_code == 400
        sha = analyze_managed_wav(project, wav(), fps=12, frames=120)["source_sha256"]
        other = projects.create_animation_project({"name": "Different project"})["id"]
        denied = client.get(f"/api/animation/projects/{other}/prompt-studio/audio-context/{sha}")
        assert denied.status_code == 409
