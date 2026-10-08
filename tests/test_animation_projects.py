from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import morphorum.animation_projects as animation_projects
from morphorum.animation_projects import (
    AnimationProjectError,
    create_animation_project,
    list_animation_projects,
    load_animation_project,
    normalize_animation_project,
    save_animation_project,
)


def test_create_animation_project_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    project = create_animation_project({"name": "My First Morph"})
    path = tmp_path / project["id"] / "project.json"

    assert path.is_file()
    assert project["schema_version"] == 2
    assert project["name"] == "My First Morph"
    assert project["animation"] == {
        "max_frames": 120,
        "fps": 24.0,
        "width": 1024,
        "height": 1024,
        "prompt_transition": "blend",
        "start_mode": "prompt",
        "source_image": "",
        "source_image_name": "",
    }
    assert project["motion"]["border_mode"] == "replicate"
    assert project["prompts"] == {"0": ""}
    assert project["motion"]["zoom"] == "0:(1.0)"
    assert project["generation"]["strength"] == "0:(0.65)"
    assert project["tracks"]["schema_version"] == 1
    assert project["tracks"]["prompts"]["positive"]["keyframes"] == [
        {"frame": 0, "value": ""}
    ]
    assert project["tracks"]["camera_2d"]["zoom"]["schedule"] == "0:(1.0)"
    assert project["camera_3d"]["translation_z"] == "0:(0)"
    assert project["camera_3d"]["fov"] == "0:(40)"
    assert project["tracks"]["camera_3d"]["translation_z"]["schedule"] == "0:(0)"
    assert project["tracks"]["camera_3d"]["fov"]["schedule"] == "0:(40)"
    assert project["tracks"]["cadence"] == {}
    assert project["tracks"]["loras"] == {}
    assert project["id"].startswith("my-first-morph-")


def test_animation_project_save_normalizes_and_preserves_unknown_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    created = create_animation_project(
        {
            "name": "Compatibility Test",
            "future_extension": {"hello": "future"},
        }
    )

    saved = save_animation_project(
        created["id"],
        {
            "name": "Compatibility Test Revised",
            "animation": {
                "max_frames": 60,
                "fps": 30,
                "width": 832,
                "height": 1216,
            },
            "prompts": {
                "0": "first",
                "30": "middle",
                "59": "last",
                "60": "out of range",
                "bad": "ignored",
            },
            "negative_prompts": {"0": "artifact"},
            "motion": {
                "angle": "0:(0), 59:(4)",
                "zoom": "0:(1.0), 59:(1.01)",
                "translation_x": "0:(0)",
                "translation_y": "0:(0)",
                "future_motion_axis": "0:(123)",
            },
            "generation": {
                "strength": "0:(0.65), 59:(0.55)",
                "noise": "0:(0.02)",
                "steps": "0:(9)",
                "guidance": "0:(0)",
                "sampler": "flowmatch_euler",
                "seed": 12345,
                "seed_behavior": "increment",
                "seed_increment": 2,
                "future_generation_value": {"keep": True},
            },
        },
    )

    assert saved["animation"]["max_frames"] == 60
    assert saved["animation"]["fps"] == 30.0
    assert saved["prompts"] == {
        "0": "first",
        "30": "middle",
        "59": "last",
    }
    assert saved["future_extension"] == {"hello": "future"}
    assert saved["motion"]["future_motion_axis"] == "0:(123)"
    assert saved["generation"]["future_generation_value"] == {"keep": True}

    loaded = load_animation_project(created["id"])
    assert loaded["id"] == created["id"]
    assert loaded["created_at"] == created["created_at"]
    assert loaded["future_extension"] == {"hello": "future"}

    summaries = list_animation_projects()
    summary = next(item for item in summaries if item["id"] == created["id"])
    assert summary["name"] == "Compatibility Test Revised"
    assert summary["id"] == created["id"]


def test_animation_project_list_returns_summaries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    first = create_animation_project({"name": "One"})
    second = create_animation_project(
        {
            "name": "Two",
            "animation": {"max_frames": 240, "fps": 12},
            "prompts": {"0": "start", "120": "change"},
        }
    )

    projects = list_animation_projects()
    ids = {item["id"] for item in projects}

    assert first["id"] in ids
    assert second["id"] in ids
    summary = next(item for item in projects if item["id"] == second["id"])
    assert summary["max_frames"] == 240
    assert summary["fps"] == 12.0
    assert summary["prompt_keyframes"] == 2


def test_animation_project_rejects_unsafe_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    with pytest.raises(AnimationProjectError, match="Invalid animation project id"):
        load_animation_project("../escape")


def test_animation_project_json_is_human_readable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    project = create_animation_project({"name": "Readable"})

    raw = (tmp_path / project["id"] / "project.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)

    assert raw.endswith("\n")
    assert "\n  \"animation\":" in raw
    assert parsed["id"] == project["id"]


def test_legacy_source_project_infers_source_start_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    project = create_animation_project({"name": "Legacy Source"})
    path = tmp_path / project["id"] / "project.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["animation"].pop("start_mode", None)
    payload["animation"]["source_image"] = "assets/source.png"
    payload["animation"]["source_image_name"] = "legacy.png"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    loaded = load_animation_project(project["id"])
    assert loaded["animation"]["start_mode"] == "source"



def test_schema_one_project_auto_migrates_tracks_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    project = create_animation_project({"name": "Legacy Timeline"})
    path = tmp_path / project["id"] / "project.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload.pop("tracks", None)
    payload["prompts"] = {"0": "forest", "60": "city"}
    payload["motion"]["zoom"] = "0:(1.0 + 0.01*sin(t)), max_f:(1.2)"
    payload["generation"]["strength"] = "0:(0.7), max_f:(0.5)"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    loaded = load_animation_project(project["id"])

    assert loaded["schema_version"] == 2
    assert loaded["tracks"]["prompts"]["positive"]["keyframes"] == [
        {"frame": 0, "value": "forest"},
        {"frame": 60, "value": "city"},
    ]
    zoom = loaded["tracks"]["camera_2d"]["zoom"]
    assert zoom["schedule"] == "0:(1.0 + 0.01*sin(t)), max_f:(1.2)"
    assert zoom["keyframes"][0]["value"] == "1.0 + 0.01*sin(t)"
    assert zoom["keyframes"][1]["frame_expression"] == "max_f"
    assert loaded["tracks"]["generation"]["strength"]["schedule"] == "0:(0.7), max_f:(0.5)"

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 2
    assert persisted["tracks"]["camera_2d"]["zoom"]["schedule"] == zoom["schedule"]


def test_legacy_editor_changes_refresh_track_mirror(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    created = create_animation_project({"name": "Legacy Bridge"})
    payload = deepcopy(created)
    payload["prompts"] = {"0": "start", "30": "middle"}
    payload["tracks"]["camera_2d"]["zoom"]["interpolation"] = "hold"
    payload["tracks"]["prompts"]["negative"]["interpolation"] = "hold"
    payload["motion"]["zoom"] = "0:(1.0), 30:(1.15)"
    payload["generation"]["strength"] = "0:(0.7), 30:(0.6)"

    saved = save_animation_project(created["id"], payload)

    assert saved["tracks"]["prompts"]["positive"]["keyframes"] == [
        {"frame": 0, "value": "start"},
        {"frame": 30, "value": "middle"},
    ]
    assert saved["tracks"]["camera_2d"]["zoom"]["schedule"] == "0:(1.0), 30:(1.15)"
    assert saved["tracks"]["camera_2d"]["zoom"]["interpolation"] == "hold"
    assert saved["tracks"]["prompts"]["negative"]["interpolation"] == "hold"
    assert saved["tracks"]["generation"]["strength"]["schedule"] == "0:(0.7), 30:(0.6)"


def test_direct_track_changes_sync_legacy_bridge(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    created = create_animation_project({"name": "Track Bridge"})
    payload = deepcopy(created)
    payload["tracks"]["camera_2d"]["zoom"]["schedule"] = "0:(1.0), 119:(1.25)"
    payload["tracks"]["prompts"]["positive"]["keyframes"] = [
        {"frame": 0, "value": "forest"},
        {"frame": 90, "value": "city"},
    ]

    saved = save_animation_project(created["id"], payload)

    assert saved["motion"]["zoom"] == "0:(1.0), 119:(1.25)"
    assert saved["prompts"] == {"0": "forest", "90": "city"}
    assert saved["tracks"]["camera_2d"]["zoom"]["keyframes"][-1] == {
        "frame": 119,
        "frame_expression": "119",
        "value": "1.25",
    }



def test_unsaved_payload_detects_legacy_changes_against_stale_tracks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    project = create_animation_project({"name": "Unsaved Preview"})
    payload = deepcopy(project)
    payload["motion"]["zoom"] = "0:(1.0), 119:(1.4)"
    payload["generation"]["strength"] = "0:(1)"

    normalized = normalize_animation_project(
        payload,
        existing=payload,
        project_id=payload["id"],
    )

    assert normalized["tracks"]["camera_2d"]["zoom"]["schedule"] == "0:(1.0), 119:(1.4)"
    assert normalized["tracks"]["generation"]["strength"]["schedule"] == "0:(1)"
