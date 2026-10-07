from __future__ import annotations

import pytest

from morphorum.animation_timeline import build_tracks_from_legacy
from morphorum.animation_resolution import (
    project_schedule_series,
    resolve_project_frame,
    validate_project_schedules,
)


def sample_project() -> dict:
    return {
        "schema_version": 1,
        "id": "phase2-test",
        "name": "Phase 2 Test",
        "animation": {
            "max_frames": 101,
            "fps": 20.0,
            "width": 1024,
            "height": 768,
            "prompt_transition": "blend",
        },
        "model": {
            "model_id": "managed:zimage-turbo",
            "family": "zimage",
            "variant": "turbo",
        },
        "prompts": {
            "0": "forest",
            "100": "city",
        },
        "negative_prompts": {
            "0": "blurry",
            "100": "noisy",
        },
        "motion": {
            "angle": "0:(0), 100:(10)",
            "zoom": "0:(1.0), 100:(1.1)",
            "translation_x": "0:(0), 100:(20)",
            "translation_y": "0:(0)",
        },
        "generation": {
            "strength": "0:(0.6), 100:(0.8)",
            "noise": "0:(0.02)",
            "steps": "0:(8), 100:(10)",
            "guidance": "0:(0)",
            "sampler": "flowmatch_euler",
            "seed": 1000,
            "seed_behavior": "increment",
            "seed_increment": 3,
        },
    }


def test_resolve_project_frame_contract() -> None:
    resolved = resolve_project_frame(sample_project(), 50)

    assert resolved["frame"] == 50
    assert resolved["time_seconds"] == pytest.approx(2.5)
    assert resolved["dimensions"] == {"width": 1024, "height": 768}
    assert resolved["motion"]["angle"] == pytest.approx(5)
    assert resolved["motion"]["zoom"] == pytest.approx(1.05)
    assert resolved["motion"]["translation_x"] == pytest.approx(10)
    assert resolved["motion"]["border_mode"] == "replicate"
    assert resolved["generation"]["strength"] == pytest.approx(0.7)
    assert resolved["generation"]["steps"] == 9
    assert resolved["generation"]["sampler"] == "flowmatch_euler"
    assert resolved["generation"]["seed"]["resolved"] == 1150

    positive = resolved["prompts"]["positive"]
    assert positive["mode"] == "blend"
    assert positive["from_text"] == "forest"
    assert positive["to_text"] == "city"
    assert positive["from_weight"] == pytest.approx(0.5)
    assert positive["to_weight"] == pytest.approx(0.5)


def test_random_seed_is_marked_for_render_time_resolution() -> None:
    project = sample_project()
    project["generation"]["seed_behavior"] = "random"
    resolved = resolve_project_frame(project, 5)

    assert resolved["generation"]["seed"]["resolved"] is None
    assert resolved["generation"]["seed"]["random_at_render"] is True


def test_validate_project_schedules_identifies_field() -> None:
    project = sample_project()
    project["motion"]["zoom"] = "0:(evil(t))"

    result = validate_project_schedules(project)

    assert result["valid"] is False
    issue = next(item for item in result["issues"] if item["field"] == "motion.zoom")
    assert issue["severity"] == "error"


def test_project_schedule_series() -> None:
    result = project_schedule_series(
        sample_project(),
        "motion.zoom",
        sample_count=10,
    )

    assert result["field"] == "motion.zoom"
    assert result["samples"][0] == {"frame": 0, "value": pytest.approx(1.0)}
    assert result["samples"][-1]["frame"] == 100
    assert result["samples"][-1]["value"] == pytest.approx(1.1)


def test_unknown_schedule_field_is_rejected() -> None:
    with pytest.raises(Exception, match="Unknown animation schedule field"):
        project_schedule_series(sample_project(), "motion.teleport")



def test_resolver_prefers_canonical_tracks_over_legacy_mirror() -> None:
    project = sample_project()
    project["schema_version"] = 2
    project["tracks"] = build_tracks_from_legacy(project)
    project["tracks"]["camera_2d"]["zoom"]["schedule"] = "0:(1.0), 100:(1.5)"
    project["tracks"]["prompts"]["positive"]["keyframes"] = [
        {"frame": 0, "value": "ocean"},
        {"frame": 100, "value": "desert"},
    ]

    resolved = resolve_project_frame(project, 50)

    assert resolved["timeline"] == {"schema_version": 1, "source": "tracks"}
    assert resolved["motion"]["zoom"] == pytest.approx(1.25)
    assert resolved["prompts"]["positive"]["from_text"] == "ocean"
    assert resolved["prompts"]["positive"]["to_text"] == "desert"
    assert resolved["prompts"]["positive"]["from_weight"] == pytest.approx(0.5)


def test_numeric_track_hold_interpolation_is_respected() -> None:
    project = sample_project()
    project["tracks"] = build_tracks_from_legacy(project)
    project["tracks"]["camera_2d"]["zoom"]["schedule"] = "0:(1.0), 100:(1.5)"
    project["tracks"]["camera_2d"]["zoom"]["interpolation"] = "hold"

    resolved = resolve_project_frame(project, 50)
    series = project_schedule_series(project, "motion.zoom", sample_count=5)

    assert resolved["motion"]["zoom"] == pytest.approx(1.0)
    assert series["interpolation"] == "hold"
    assert series["samples"][2]["value"] == pytest.approx(1.0)


def test_prompt_tracks_can_use_independent_transition_modes() -> None:
    project = sample_project()
    project["tracks"] = build_tracks_from_legacy(project)
    project["tracks"]["prompts"]["positive"]["interpolation"] = "hold"
    project["tracks"]["prompts"]["negative"]["interpolation"] = "blend"

    resolved = resolve_project_frame(project, 50)

    positive = resolved["prompts"]["positive"]
    negative = resolved["prompts"]["negative"]
    assert positive["mode"] == "hold"
    assert positive["from_text"] == "forest"
    assert positive["to_weight"] == pytest.approx(0.0)
    assert negative["mode"] == "blend"
    assert negative["from_weight"] == pytest.approx(0.5)
    assert negative["to_weight"] == pytest.approx(0.5)
