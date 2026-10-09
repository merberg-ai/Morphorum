from __future__ import annotations

import json

import pytest

import morphorum.animation_projects as animation_projects
import morphorum.deforum_import as deforum_import
from morphorum.deforum_import import (
    DeforumImportError,
    create_deforum_import,
    parse_deforum_source,
    preview_deforum_import,
)


def _model(family: str = "sdxl") -> dict:
    return {
        "id": "model-1",
        "kind": "checkpoints",
        "family": family,
        "variant": "sdxl" if family == "sdxl" else ("dev" if family == "flux" else "turbo"),
        "name": "Indexed Test Model",
        "filename": "model.safetensors",
        "path": "/not/used/by/importer/model.safetensors",
    }


def _source() -> dict:
    return {
        "batch_name": "Legacy project",
        "max_frames": 48,
        "fps": 12,
        "W": 768,
        "H": 768,
        "animation_mode": "2D",
        "animation_prompts": {
            "0": "a haunted computer",
            "24": "a haunted computer <lora:detail:0.7>",
        },
        "negative_prompt": "blurry",
        "angle": "0:(0), 24:(4)",
        "zoom": "0:(1.0), 24:(1.01)",
        "translation_x": "0:(0), 24:(8)",
        "translation_y": 0,
        "strength_schedule": "0:(0.65)",
        "noise_schedule": "0:(0.02)",
        "steps": 22,
        "cfg_scale": 6.5,
        "diffusion_cadence": 3,
        "seed": 1234,
        "seed_behavior": "iter",
        "seed_iter_N": 2,
        "sampler": "Euler a",
        "model_path": r"C:\\danger\\legacy.safetensors",
        "hybrid_video_motion": "Optical Flow",
        "mystery_setting": {"future": True},
    }


def test_parse_rejects_non_json_txt_without_executing() -> None:
    with pytest.raises(DeforumImportError, match="not JSON-serialized"):
        parse_deforum_source(
            "max_frames = 120\n__import__('os').system('nope')",
            filename="settings.txt",
        )


def test_parse_rejects_oversized_and_nested_payloads() -> None:
    with pytest.raises(DeforumImportError, match="too large"):
        parse_deforum_source(
            json.dumps({"value": "x" * deforum_import.MAX_SOURCE_BYTES}),
            filename="settings.json",
        )

    nested: dict = {"value": 1}
    for _ in range(deforum_import.MAX_NESTING_DEPTH + 2):
        nested = {"next": nested}
    with pytest.raises(DeforumImportError, match="nesting depth"):
        parse_deforum_source(json.dumps(nested), filename="settings.json")


def test_preview_maps_core_2d_settings_and_never_trusts_model_path(monkeypatch) -> None:
    monkeypatch.setattr(deforum_import, "get_model", lambda _model_id: _model("sdxl"))
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    preview = preview_deforum_import(
        json.dumps(_source()),
        filename=r"..\\unsafe\\settings.json",
        model_id="model-1",
    )
    project = preview["project"]
    assert preview["can_create"] is True
    assert preview["source_filename"] == "settings.json"
    assert project["animation"]["max_frames"] == 48
    assert project["animation"]["fps"] == 12
    assert project["animation"]["width"] == 768
    assert project["animation"]["height"] == 768
    assert project["animation"]["mode"] == "2d"
    assert project["prompts"]["24"].endswith("<lora:detail:0.7>")
    assert project["negative_prompts"]["0"] == "blurry"
    assert project["motion"]["angle"] == "0:(0), 24:(4)"
    assert project["motion"]["translation_x"] == "0:(0), 24:(8)"
    assert project["generation"]["steps"] == "0:(22)"
    assert project["generation"]["guidance"] == "0:(6.5)"
    assert project["generation"]["sampler"] == "euler_a"
    assert project["generation"]["seed_behavior"] == "increment"
    assert project["generation"]["seed_increment"] == 2
    assert project["cadence"]["diffusion"] == "0:(3)"
    assert project["model"]["model_id"] == "model-1"
    assert project["compatibility"]["deforum"]["source_settings"]["model_path"].startswith("C:")
    assert project["model"]["model_id"] != project["compatibility"]["deforum"]["source_settings"]["model_path"]
    assert "hybrid_video_motion" in preview["unsupported_keys"]
    assert "mystery_setting" in preview["unmapped_keys"]
    path_mapping = next(item for item in preview["mappings"] if item["source_key"] == "model_path")
    assert path_mapping["status"] == "ignored_path"


def test_preview_without_model_is_dry_run_and_requires_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    preview = preview_deforum_import(
        json.dumps({"max_frames": 12, "animation_prompts": {"0": "test"}}),
        filename="settings.json",
    )
    assert preview["model_required"] is True
    assert preview["can_create"] is False
    assert preview["project"]["model"]["model_id"] == ""
    assert any("No Morphorum model selected" in item for item in preview["warnings"])


def test_3d_mapping_is_explicitly_warning_marked(monkeypatch) -> None:
    monkeypatch.setattr(deforum_import, "get_model", lambda _model_id: _model("sdxl"))
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    preview = preview_deforum_import(
        json.dumps(
            {
                "animation_mode": "3D",
                "max_frames": 30,
                "translation_x": "0:(1)",
                "translation_z": "0:(0.05)",
                "rotation_3d_y": "0:(0.5)",
            }
        ),
        model_id="model-1",
    )
    project = preview["project"]
    assert project["animation"]["mode"] == "3d"
    assert project["camera_3d"]["translation_x"] == "0:(1)"
    assert project["camera_3d"]["translation_z"] == "0:(0.05)"
    assert project["camera_3d"]["rotation_y"] == "0:(0.5)"
    statuses = {
        item["source_key"]: item["status"]
        for item in preview["mappings"]
        if item["source_key"] in {"translation_x", "translation_z", "rotation_3d_y"}
    }
    assert statuses == {
        "translation_x": "mapped_with_warning",
        "translation_z": "mapped_with_warning",
        "rotation_3d_y": "mapped_with_warning",
    }


def test_invalid_schedule_falls_back_without_eval(monkeypatch) -> None:
    monkeypatch.setattr(deforum_import, "get_model", lambda _model_id: _model("sdxl"))
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    preview = preview_deforum_import(
        json.dumps(
            {
                "max_frames": 12,
                "angle": "0:(__import__('os').system('nope'))",
            }
        ),
        model_id="model-1",
    )
    assert preview["project"]["motion"]["angle"] == "0:(0)"
    mapping = next(item for item in preview["mappings"] if item["source_key"] == "angle")
    assert mapping["status"] == "rejected"
    assert any("schedule is invalid" in item for item in preview["warnings"])


def test_sampler_is_repaired_for_selected_family(monkeypatch) -> None:
    monkeypatch.setattr(deforum_import, "get_model", lambda _model_id: _model("flux"))
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    preview = preview_deforum_import(
        json.dumps({"sampler": "Euler a"}),
        model_id="model-1",
    )
    assert preview["project"]["generation"]["sampler"] == "flowmatch_euler"
    assert any("not supported by flux" in item for item in preview["warnings"])


def test_create_retranslates_and_creates_new_native_project(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(deforum_import, "get_model", lambda _model_id: _model("sdxl"))
    monkeypatch.setattr(
        deforum_import,
        "validate_project_schedules",
        lambda project: {"valid": True, "issues": [], "fields": {}},
    )
    monkeypatch.setattr(animation_projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(deforum_import, "create_animation_project", animation_projects.create_animation_project)

    project, report = create_deforum_import(
        json.dumps({"batch_name": "Imported", "max_frames": 10, "animation_prompts": {"0": "hello"}}),
        filename="legacy.json",
        model_id="model-1",
        project_name="Imported Copy",
    )
    assert project["id"] != "deforum-preview"
    assert project["name"] == "Imported Copy"
    assert project["schema_version"] == 2
    assert project["tracks"]["prompts"]["positive"]["keyframes"][0]["value"] == "hello"
    assert project["compatibility"]["deforum"]["source_filename"] == "legacy.json"
    assert report["source_sha256"] == project["compatibility"]["deforum"]["source_sha256"]
    assert (tmp_path / project["id"] / "project.json").is_file()


def test_create_requires_explicit_indexed_model() -> None:
    with pytest.raises(DeforumImportError, match="Choose an indexed Morphorum checkpoint"):
        create_deforum_import(
            json.dumps({"max_frames": 10}),
            filename="legacy.json",
            model_id="",
        )
