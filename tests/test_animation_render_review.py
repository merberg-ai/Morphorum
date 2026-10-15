"""MS5.2 read-only review of complete, frame-aligned historical renders."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_render as render
import morphorum.animation_projects as projects
from morphorum.app import app


@pytest.fixture
def fixture_render(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        response = client.post("/api/animation/projects", json={"name": "MS5.2 Review"})
        assert response.status_code == 201
        project_id = response.json()["project"]["id"]
        folder = tmp_path / "outputs" / "animations" / project_id / "review-take"
        frames = folder / "frames"
        frames.mkdir(parents=True)
        for frame in range(4):
            (frames / f"frame_{frame:06d}.png").write_bytes(b"test png backing file")
        manifest = {
            "schema_version": 1, "project_id": project_id, "id": "review-take",
            "status": "completed", "total_frames": 4,
            "project": {"animation": {"fps": 24, "max_frames": 4}},
            "results": [{"frame": n, "filename": f"frame_{n:06d}.png"} for n in range(4)],
        }
        path = folder / "render-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        yield client, project_id, manifest, path, frames


def test_review_metadata_requires_complete_frozen_render_and_all_pngs(fixture_render):
    client, project_id, manifest, path, frames = fixture_render
    url = f"/api/animation/renders/{project_id}/review-take/review-metadata"
    valid = client.get(url)
    assert valid.status_code == 200, valid.text
    assert valid.json() == {
        "project_id": project_id, "render_id": "review-take",
        "status": "completed", "fps": 24.0, "frames": 4,
        "recorded_frames": 4, "ready": True, "issues": [],
    }
    before = path.read_bytes()
    assert client.get(url).status_code == 200
    assert path.read_bytes() == before, "Read-only metadata must not mutate saved render"

    (frames / "frame_000002.png").unlink()
    missing = client.get(url)
    assert missing.status_code == 200
    assert not missing.json()["ready"]
    assert "PNG" in " ".join(missing.json()["issues"])
    (frames / "frame_000002.png").write_bytes(b"restored")


@pytest.mark.parametrize("change", [
    {"status": "interrupted"},
    {"status": "failed"},
    {"total_frames": 5},
    {"results": [{"frame": 0}, {"frame": 1}]},
    {"results": [{"frame": 0}, {"frame": 1}, {"frame": 1}, {"frame": 3}]},
    {"results": [{"frame": 0}, {"frame": 2}, {"frame": 3}, {"frame": 4}]},
    {"project": {"animation": {"fps": 0, "max_frames": 4}}},
    {"project": {"animation": {"fps": 24, "max_frames": 3}}},
])
def test_invalid_or_partial_manifest_refused(fixture_render, change):
    client, project_id, manifest, path, _ = fixture_render
    manifest.update(change)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    response = client.get(f"/api/animation/renders/{project_id}/review-take/review-metadata")
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is False
    assert response.json()["issues"]


def test_render_review_project_identity_and_unreadable_manifest_guard(fixture_render):
    client, project_id, manifest, path, _ = fixture_render
    base = f"/api/animation/renders/{project_id}/review-take/review-metadata"
    manifest["project_id"] = "other-project"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert client.get(base).status_code == 404
    path.write_text("{bad json", encoding="utf-8")
    assert client.get(base).status_code == 404
    assert client.get(f"/api/animation/renders/{project_id}/no-such-render/review-metadata").status_code == 404
