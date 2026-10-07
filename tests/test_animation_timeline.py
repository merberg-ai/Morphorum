from __future__ import annotations

from copy import deepcopy

import pytest

from morphorum.animation_projects import normalize_animation_project
from morphorum.animation_resolution import resolve_project_timeline
from morphorum.animation_timeline import (
    TimelineError,
    delete_track_keyframe,
    get_timeline_track,
    move_track_keyframe,
    set_track_interpolation,
    timeline_snapshot,
    timeline_track_descriptors,
    upsert_track_keyframe,
)


def sample_project(max_frames: int = 20) -> dict:
    return normalize_animation_project(
        {
            "id": "timeline-a2-test",
            "name": "Timeline A2 Test",
            "animation": {
                "max_frames": max_frames,
                "fps": 10,
            },
            "prompts": {"0": "forest"},
            "negative_prompts": {"0": "blurry"},
            "motion": {
                "angle": "0:(0)",
                "zoom": "0:(1.0)",
                "translation_x": "0:(0)",
                "translation_y": "0:(0)",
            },
            "generation": {
                "strength": "0:(0.65)",
                "noise": "0:(0.02)",
                "steps": "0:(8)",
                "guidance": "0:(0)",
                "sampler": "flowmatch_euler",
                "seed": 100,
                "seed_behavior": "fixed",
                "seed_increment": 1,
            },
        },
        project_id="timeline-a2-test",
    )


def test_timeline_descriptors_expose_canonical_tracks_and_reserved_groups() -> None:
    descriptors = timeline_track_descriptors()

    groups = {item["id"]: item for item in descriptors["groups"]}
    tracks = {item["id"]: item for item in descriptors["tracks"]}

    assert descriptors["schema_version"] == 1
    assert groups["camera_3d"]["reserved"] is True
    assert groups["cadence"]["reserved"] is True
    assert groups["loras"]["reserved"] is True
    assert tracks["prompts.positive"]["interpolation_modes"] == ["blend", "hold"]
    assert tracks["camera_2d.zoom"]["legacy_field"] == "motion.zoom"
    assert tracks["generation.steps"]["value_type"] == "integer"


def test_numeric_keyframe_crud_updates_schedule_and_legacy_bridge() -> None:
    project = sample_project()

    upsert_track_keyframe(
        project,
        "camera_2d",
        "zoom",
        frame=10,
        value="1.2 + 0.01*sin(t)",
    )

    track = get_timeline_track(project, "camera_2d", "zoom")["track"]
    assert track["schedule"] == "0:(1.0), 10:(1.2 + 0.01*sin(t))"
    assert track["keyframes"][-1] == {
        "frame": 10,
        "frame_expression": "10",
        "value": "1.2 + 0.01*sin(t)",
    }
    assert project["motion"]["zoom"] == track["schedule"]

    move_track_keyframe(
        project,
        "camera_2d",
        "zoom",
        source_frame=10,
        target_frame=12,
    )
    moved = get_timeline_track(project, "camera_2d", "zoom")["track"]
    assert moved["schedule"] == "0:(1.0), 12:(1.2 + 0.01*sin(t))"
    assert moved["keyframes"][-1]["frame_expression"] == "12"

    delete_track_keyframe(project, "camera_2d", "zoom", frame=12)
    reduced = get_timeline_track(project, "camera_2d", "zoom")["track"]
    assert reduced["keyframes"] == [
        {"frame": 0, "frame_expression": "0", "value": "1.0"}
    ]
    assert project["motion"]["zoom"] == "0:(1.0)"


def test_prompt_keyframe_crud_preserves_required_frame_zero() -> None:
    project = sample_project()

    upsert_track_keyframe(
        project,
        "prompts",
        "positive",
        frame=10,
        value="city",
    )
    assert project["prompts"] == {"0": "forest", "10": "city"}

    move_track_keyframe(
        project,
        "prompts",
        "positive",
        source_frame=10,
        target_frame=14,
    )
    assert project["prompts"] == {"0": "forest", "14": "city"}

    delete_track_keyframe(project, "prompts", "positive", frame=14)
    assert project["prompts"] == {"0": "forest"}

    with pytest.raises(TimelineError, match="requires a frame 0"):
        delete_track_keyframe(project, "prompts", "positive", frame=0)

    with pytest.raises(TimelineError, match="requires its frame 0"):
        move_track_keyframe(
            project,
            "prompts",
            "positive",
            source_frame=0,
            target_frame=5,
        )


def test_move_collision_requires_explicit_overwrite() -> None:
    project = sample_project()
    upsert_track_keyframe(project, "generation", "strength", frame=5, value="0.7")
    upsert_track_keyframe(project, "generation", "strength", frame=10, value="0.5")

    with pytest.raises(TimelineError, match="already has a keyframe"):
        move_track_keyframe(
            project,
            "generation",
            "strength",
            source_frame=5,
            target_frame=10,
        )

    move_track_keyframe(
        project,
        "generation",
        "strength",
        source_frame=5,
        target_frame=10,
        overwrite=True,
    )
    track = get_timeline_track(project, "generation", "strength")["track"]
    assert [item["frame"] for item in track["keyframes"]] == [0, 10]
    assert track["keyframes"][-1]["value"] == "0.7"


def test_interpolation_is_per_track_and_legacy_prompt_mode_tracks_positive() -> None:
    project = sample_project()

    set_track_interpolation(
        project,
        "prompts",
        "negative",
        interpolation="hold",
    )
    prompts = project["tracks"]["prompts"]
    assert prompts["positive"]["interpolation"] == "blend"
    assert prompts["negative"]["interpolation"] == "hold"
    assert project["animation"]["prompt_transition"] == "blend"

    set_track_interpolation(
        project,
        "camera_2d",
        "zoom",
        interpolation="hold",
    )
    assert project["tracks"]["camera_2d"]["zoom"]["interpolation"] == "hold"
    assert project["motion"]["zoom"] == "0:(1.0)"

    with pytest.raises(TimelineError, match="does not support"):
        set_track_interpolation(
            project,
            "camera_2d",
            "zoom",
            interpolation="bezier",
        )


def test_timeline_snapshot_is_frontend_ready() -> None:
    project = sample_project(max_frames=30)
    snapshot = timeline_snapshot(project)

    assert snapshot["project_id"] == "timeline-a2-test"
    assert snapshot["max_frames"] == 30
    assert snapshot["fps"] == 10.0
    assert snapshot["duration_seconds"] == pytest.approx(3.0)
    assert snapshot["tracks"]["camera_2d"]["zoom"]["kind"] == "numeric"
    assert snapshot["descriptors"]["tracks"]


def test_resolve_project_timeline_returns_requested_range() -> None:
    project = sample_project(max_frames=21)
    upsert_track_keyframe(project, "camera_2d", "zoom", frame=20, value="1.2")
    upsert_track_keyframe(project, "prompts", "positive", frame=20, value="city")

    resolved = resolve_project_timeline(
        project,
        start_frame=0,
        end_frame=20,
        step=10,
    )

    assert resolved["count"] == 3
    assert [item["frame"] for item in resolved["frames"]] == [0, 10, 20]
    assert resolved["frames"][1]["motion"]["zoom"] == pytest.approx(1.1)
    assert resolved["frames"][1]["prompts"]["positive"]["to_weight"] == pytest.approx(0.5)


def test_track_edit_validation_rejects_bad_frame_and_empty_numeric_value() -> None:
    project = sample_project()

    with pytest.raises(TimelineError, match="outside the animation range"):
        upsert_track_keyframe(
            project,
            "camera_2d",
            "zoom",
            frame=20,
            value="1.1",
        )

    with pytest.raises(TimelineError, match="cannot be empty"):
        upsert_track_keyframe(
            project,
            "camera_2d",
            "zoom",
            frame=10,
            value="",
        )

    with pytest.raises(TimelineError, match="Invalid keyframe"):
        upsert_track_keyframe(
            project,
            "camera_2d",
            "zoom",
            frame=10,
            value="evil(t)",
        )

    with pytest.raises(TimelineError, match="Unknown timeline track"):
        get_timeline_track(project, "camera_3d", "teleport")
