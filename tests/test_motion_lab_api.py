from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import morphorum.animation_projects as projects
from morphorum.app import app


def preset(name="wave", **kwargs):
    return {
        "id": "ml0-layer", "preset": name, "blend": "add",
        "strength": 0.7, "cycle_seconds": 2.0, "fade_seconds": 0.2,
        "start_frame": 0, "end_frame": 24,
        **kwargs,
    }


def test_motion_lab_preview_apply_persists_real_native_camera_tracks(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "Lab API"})
        assert created.status_code == 201
        project = created.json()["project"]
        project["animation"]["mode"] = "3d"
        project["animation"]["max_frames"] = 24
        project["animation"]["fps"] = 12
        saved = client.put("/api/animation/projects/" + project["id"], json=project)
        assert saved.status_code == 200, saved.text

        url = "/api/animation/projects/" + project["id"] + "/motion-lab"
        presets = client.get("/api/animation/motion-lab/presets")
        assert presets.status_code == 200
        assert "spiral" in presets.json()["presets"]

        preview = client.post(url + "/preview", json={"layers": [preset("spiral")]})
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "preview"
        assert preview.json()["diagnostics"]["layer_count"] == 1
        series = preview.json()["diagnostics"]["series"]
        assert len(series["translation_z"]) == 24
        assert len(series["rotation_z"]) == 24
        assert series["translation_z"][0] == 0
        assert series["translation_z"][12] > 0
        assert "translation_z" in preview.json()["project"]["camera_3d"]
        untouched = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert untouched["camera_3d"]["translation_z"] == "0:(0)"

        applied = client.post(url + "/apply", json={"layers": [preset("spiral")]})
        assert applied.status_code == 200, applied.text
        assert applied.json()["status"] == "applied"
        loaded = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert loaded["motion_lab"]["layers"][0]["preset"] == "spiral"
        assert loaded["camera_3d"]["translation_z"] != "0:(0)"
        assert loaded["tracks"]["camera_3d"]["translation_z"]["schedule"] == loaded["camera_3d"]["translation_z"]

        resolved = client.post("/api/animation/resolve-frame", json={"project": loaded, "frame": 12})
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolved"]["camera_3d"]["translation_z"] > 0

        repeated = client.post(url + "/apply", json={"layers": [preset("spiral")]})
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["project"]["camera_3d"]["translation_z"] == loaded["camera_3d"]["translation_z"]

        # A hand-edited timeline after Motion Lab applied it must cause a
        # clear conflict rather than silently losing the user's schedule.
        edits = repeated.json()["project"]
        edits["tracks"]["camera_3d"]["translation_z"]["schedule"] = "0:(0.07)"
        edits["camera_3d"]["translation_z"] = "0:(0.07)"
        updated = client.put("/api/animation/projects/" + project["id"], json=edits)
        assert updated.status_code == 200, updated.text
        conflict = client.post(url + "/apply", json={"layers": [preset("wave")]})
        assert conflict.status_code == 409
        assert "changed since" in conflict.json()["detail"]
        still_edited = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert still_edited["camera_3d"]["translation_z"] == "0:(0.07)"

        # Preview is never blocked by this conflict or written to project.json.
        # It shows the latest Editor camera as a temporary new baseline.
        draft = client.post(url + "/preview", json={"layers": [preset("wave")]})
        assert draft.status_code == 200, draft.text
        assert draft.json()["diagnostics"]["camera_changed"] is True
        assert draft.json()["diagnostics"]["rebased"] is True
        assert draft.json()["project"]["motion_lab"]["base_tracks"]["translation_z"]["schedule"] == "0:(0.07)"
        still_edited = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert still_edited["camera_3d"]["translation_z"] == "0:(0.07)"

        # Explicit confirmation is expressed by rebase_current=True.
        rebased = client.post(url + "/apply",
            json={"layers": [preset("wave")], "rebase_current": True})
        assert rebased.status_code == 200, rebased.text
        assert rebased.json()["diagnostics"]["rebased"] is True
        reloaded = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert reloaded["motion_lab"]["base_tracks"]["translation_z"]["schedule"] == "0:(0.07)"
        assert reloaded["camera_3d"]["translation_z"] != loaded["camera_3d"]["translation_z"]
        # Reapplication of a rebased layer can never double-apply that layer.
        same = client.post(url + "/apply", json={"layers": [preset("wave")]})
        assert same.status_code == 200, same.text
        assert same.json()["project"]["camera_3d"]["translation_x"] == reloaded["camera_3d"]["translation_x"]


def test_motion_lab_preview_rejects_invalid_layer_and_2d_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "Lab 2D"})
        project_id = created.json()["project"]["id"]
        base = "/api/animation/projects/" + project_id + "/motion-lab"
        mismatch = client.post(base + "/preview", json={"layers": [preset()]})
        assert mismatch.status_code == 400
        assert "3D animation mode" in mismatch.json()["detail"]
        no_layers = client.post(base + "/preview", json={})
        assert no_layers.status_code == 400
        assert "list" in no_layers.json()["detail"]



def test_motion_lab_preview_includes_unsaved_editor_camera_without_persisting(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as client:
        created = client.post("/api/animation/projects", json={"name": "Draft camera"})
        project = created.json()["project"]
        project["animation"]["mode"] = "3d"
        project["animation"]["max_frames"] = 24
        project["animation"]["fps"] = 12
        saved = client.put("/api/animation/projects/" + project["id"], json=project)
        assert saved.status_code == 200
        project = saved.json()["project"]
        # Mimic a handwritten camera schedule in Editor, not yet saved.
        edited = dict(project)
        edited["camera_3d"] = {**project["camera_3d"], "translation_y": "0:(0.04)"}
        preview = client.post(
            "/api/animation/projects/" + project["id"] + "/motion-lab/preview",
            json={"layers": [preset("spiral")], "project": edited},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["project"]["motion_lab"]["base_tracks"]["translation_y"]["schedule"] == "0:(0.04)"
        on_disk = client.get("/api/animation/projects/" + project["id"]).json()["project"]
        assert on_disk["camera_3d"]["translation_y"] == "0:(0)"
