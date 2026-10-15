"""MS4.3 named motion presets: shared storage, strict validation, CRUD and isolation."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_projects as projects
import morphorum.motion_studio_presets as library
from morphorum.app import app


def form(**changes):
    values = {
        "name": "Cinematic Orbit",
        "preset": "spiral",
        "blend": "replace",
        "axes": ["translation_x", "rotation_z"],
        "strength": 0.65,
        "cycle_seconds": 3.5,
        "fade_seconds": 0.25,
        "start_ratio": 0.2,
        "end_ratio": 0.75,
    }
    values.update(changes)
    return values


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path / "projects")
    with TestClient(app) as instance:
        yield instance


def test_saved_presets_are_global_project_independent_and_reopen(client):
    a = client.post("/api/animation/projects", json={"name": "First Project"})
    assert a.status_code == 201
    a_id = a.json()["project"]["id"]

    url = "/api/animation/motion-studio/custom-presets"
    assert client.get(url).json() == {"presets": []}
    response = client.post(url, json=form())
    assert response.status_code == 201, response.text
    saved = response.json()["preset"]
    assert len(saved["id"]) == 32
    assert saved["name"] == "Cinematic Orbit"
    assert saved["start_ratio"] == .2
    assert saved["axes"] == ["translation_x", "rotation_z"]
    assert saved in client.get(url).json()["presets"]
    assert json.loads(library._file().read_text(encoding="utf-8"))["version"] == 1

    b = client.post("/api/animation/projects", json={"name": "Second Project"})
    assert b.status_code == 201
    for project_id in (a_id, b.json()["project"]["id"]):
        project = client.get("/api/animation/projects/" + project_id).json()["project"]
        assert not project.get("motion_lab", {}).get("layers")
    # Persisted on disk, not in an in-memory singleton or a project.
    assert library.list_custom_presets() == [saved]


def test_update_delete_and_duplicate_names_do_not_change_project_layers(client):
    base = "/api/animation/motion-studio/custom-presets"
    original = client.post(base, json=form())
    saved = original.json()["preset"]
    duplicate = client.post(base, json=form(name="cinematic orbit"))
    assert duplicate.status_code == 409
    renamed = client.put(base + "/" + saved["id"], json=form(
        name="Gentle Sweep", preset="wave", blend="add",
        axes=["translation_y"], start_ratio=0, end_ratio=1))
    assert renamed.status_code == 200, renamed.text
    changed = renamed.json()["preset"]
    assert changed["id"] == saved["id"]
    assert changed["preset"] == "wave"
    assert changed["axes"] == ["translation_y"]
    assert changed["end_ratio"] == 1
    assert len(client.get(base).json()["presets"]) == 1

    second = client.post(base, json=form(name="Another Motion"))
    assert second.status_code == 201
    conflicting = client.put(base + "/" + second.json()["preset"]["id"],
                             json=form(name="GENTLE SWEEP"))
    assert conflicting.status_code == 409
    assert client.delete(base + "/" + saved["id"]).status_code == 200
    assert client.delete(base + "/" + saved["id"]).status_code == 404
    assert client.put(base + "/missing", json=form()).status_code == 404
    assert [r["name"] for r in client.get(base).json()["presets"]] == ["Another Motion"]


@pytest.mark.parametrize("patch", [
    {"name": ""}, {"name": "n" * 65}, {"name": "Unsafe\\nname"},
    {"preset": "anything"}, {"blend": "multiply"},
    {"preset": "still", "blend": "add"},
    {"axes": []}, {"axes": ["translation_x", "translation_x"]},
    {"axes": ["rotation_x"]}, {"strength": 1.5},
    {"strength": float("inf")}, {"strength": "0.5"},
    {"cycle_seconds": .1}, {"fade_seconds": -1},
    {"start_ratio": -.1}, {"end_ratio": 1.1},
    {"start_ratio": .8, "end_ratio": .8},
    {"start_ratio": .9, "end_ratio": .2},
])
def test_invalid_library_entries_are_rejected_and_never_written(client, patch):
    result = client.post("/api/animation/motion-studio/custom-presets",
                         json=form(**patch))
    assert result.status_code in (400, 422), result.text
    assert client.get("/api/animation/motion-studio/custom-presets").json() == {"presets": []}


def test_corrupt_preset_file_is_not_silently_overwritten(client):
    path = library._file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken json", encoding="utf-8")
    assert client.get("/api/animation/motion-studio/custom-presets").status_code == 400
    assert client.post("/api/animation/motion-studio/custom-presets",
                       json=form()).status_code == 400
    assert path.read_text(encoding="utf-8") == "{broken json"


def test_library_max_64_entries(client):
    base = "/api/animation/motion-studio/custom-presets"
    for index in range(64):
        assert client.post(base, json=form(name=f"Motion {index:02d}")).status_code == 201
    assert client.post(base, json=form(name="Overflow")).status_code == 409
    assert len(client.get(base).json()["presets"]) == 64
