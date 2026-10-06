from __future__ import annotations

import json
from pathlib import Path

import pytest

import morphorum.animation_projects as animation_projects
from morphorum.animation_projects import (
    AnimationProjectError,
    create_animation_project,
    list_animation_projects,
    load_animation_project,
    save_animation_project,
)


def test_create_animation_project_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)

    project = create_animation_project({"name": "My First Morph"})
    path = tmp_path / project["id"] / "project.json"

    assert path.is_file()
    assert project["schema_version"] == 1
    assert project["name"] == "My First Morph"
    assert project["animation"] == {
        "max_frames": 120,
        "fps": 24.0,
        "width": 1024,
        "height": 1024,
    }
    assert project["prompts"] == {"0": ""}
    assert project["motion"]["zoom"] == "0:(1.0)"
    assert project["generation"]["strength"] == "0:(0.65)"


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
