from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import morphorum.animation_preflight as preflight
from morphorum.animation_projects import normalize_animation_project


def project():
    p = {
        "id": "test-preflight", "name": "Preflight",
        "animation": {"max_frames": 4, "width": 1024, "height": 1024,
                      "fps": 12, "mode": "2d", "start_mode": "prompt"},
        "model": {"model_id": "sample-model", "family": "sdxl"},
        "prompts": {"0": "A small orange cat"},
        "generation": {"steps": "0:(20)", "guidance": "0:(6)", "sampler": "euler"},
    }
    return normalize_animation_project(p, existing=p, project_id=p["id"])


def index_model(checkpoint: Path):
    return {"id": "sample-model", "kind": "checkpoints", "family": "sdxl",
            "variant": "sdxl", "name": "Sample", "source": "external",
            "path": str(checkpoint)}


def test_valid_preflight_is_read_only(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock checkpoint for file presence")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    before = deepcopy(p)
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert report["valid"], report["issues"]
    assert report["errors"] == 0
    assert report["checked_frames"] == 4
    assert p == before


def test_sampler_and_guidance_reject_bad_model_settings(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    p["generation"]["sampler"] = "flowmatch_euler"
    p["generation"]["guidance"] = "0:(50)"
    # Match API behavior: merge edited schedules into canonical project tracks.
    p = normalize_animation_project(p, existing=p, project_id=p["id"])
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert not report["valid"]
    assert {"generation.sampler", "generation.guidance"} <= {
        issue["field"] for issue in report["issues"] if issue["severity"] == "error"
    }


def test_missing_checkpoint_and_source_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "get_model", lambda _id: None)
    p = project()
    p["animation"]["start_mode"] = "source"
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert not report["valid"]
    fields = {issue["field"] for issue in report["issues"]}
    assert "animation.source_image" in fields
    assert "model.model_id" in fields
    assert any(issue["action"] == "models" for issue in report["issues"])


def test_unsupported_dimensions_and_prompt_fail_before_render(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    p["animation"]["width"] = 1025
    p["prompts"]["0"] = ""
    # Normalize again so the prompt track matches the current blank text.
    p = normalize_animation_project(p, existing=p, project_id=p["id"])
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert not report["valid"]
    fields = {issue["field"] for issue in report["issues"]}
    assert "animation.width" in fields
    assert "tracks.prompts.positive" in fields


def test_very_long_render_discloses_sampled_frames(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    p["animation"]["max_frames"] = 520
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert report["valid"], report["issues"]
    assert report["checked_frames"] <= 500
    assert any(issue["severity"] == "warning" and
               "sampled" not in issue["message"].lower()
               for issue in report["issues"])


def test_sdxl_schedule_preflight_rejects_incompatible_and_unknown_values(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    p["generation"]["sampler"] = "ddim"
    p["generation"]["schedule_type"] = "karras"
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert not report["valid"]
    assert any(
        issue["field"] == "generation.schedule_type" and "DDIM" in issue["message"]
        for issue in report["issues"]
    )
    p["generation"]["sampler"] = "euler"
    p["generation"]["schedule_type"] = "unsupported"
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert not report["valid"]
    assert any(
        issue["field"] == "generation.schedule_type"
        for issue in report["issues"] if issue["severity"] == "error"
    )


def test_sdxl_karras_euler_passes_animation_preflight(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"mock")
    monkeypatch.setattr(preflight, "get_model", lambda _id: index_model(checkpoint))
    p = project()
    p["generation"]["schedule_type"] = "karras"
    report = preflight.check_animation_render_preflight(p, tmp_path / "missing.png")
    assert report["valid"], report["issues"]
