"""DA4.1 Motion Director cue document and source binding regression tests."""
import json
import math

import pytest

from morphorum import audio_motion_cues as cues
from morphorum.audio_motion import AudioMotionError

HASH = "a" * 64


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(cues, "animation_project_directory", lambda _: tmp_path)
    audio_dir = tmp_path / "motion_lab_audio"
    audio_dir.mkdir()
    (audio_dir / (HASH + ".wav")).write_bytes(b"RIFF")
    return tmp_path


def document():
    return {"source_sha256": HASH, "duration_seconds": 16.26, "cues": [
        {"id": "roll", "preset": "roll_right_left", "time_seconds": 3.5,
         "intensity": .4, "duration_seconds": .75, "enabled": True},
        {"id": "riff", "preset": "push_zoom_in", "time_seconds": 0.2,
         "intensity": .6, "duration_seconds": 1.2, "enabled": True},
    ]}


def test_manual_cues_roundtrip_without_detector_events(project):
    source = document()
    saved = cues.save_motion_cues("project", source)
    assert [cue["id"] for cue in saved["cues"]] == ["riff", "roll"]
    assert all(cue["source_event_id"] is None for cue in saved["cues"])
    assert cues.load_motion_cues("project", HASH) == saved
    assert saved["schema_version"] == 1


def test_cues_accept_simultaneous_motions(project):
    obj = document()
    obj["cues"][1]["time_seconds"] = 3.5
    normalized = cues.save_motion_cues("project", obj)
    assert len(normalized["cues"]) == 2


@pytest.mark.parametrize("change", [
    ("source_sha256", "b" * 64),
    ("source_sha256", "../bad"),
    ("duration_seconds", math.nan),
    ("cues", [{"id": "x", "preset": "unknown", "time_seconds": 1}]),
    ("cues", [{"id": "x", "preset": "shake", "time_seconds": 18}]),
    ("cues", [{"id": "x", "preset": "shake", "time_seconds": 2, "intensity": 1.2}]),
    ("cues", [{"id": "x", "preset": "shake", "time_seconds": 2, "duration_seconds": -1}]),
    ("cues", [{"id": "x", "preset": "shake", "time_seconds": 2, "enabled": 1}]),
    ("cues", [{"id": "x", "preset": "shake", "time_seconds": 2},
              {"id": "x", "preset": "shake", "time_seconds": 3}]),
])
def test_reject_invalid_cues(project, change):
    obj = document()
    obj[change[0]] = change[1]
    with pytest.raises(AudioMotionError):
        cues.save_motion_cues("project", obj)


def test_mismatched_stored_file_is_rejected(project):
    path = project / "motion_lab_audio" / (HASH + ".cues.json")
    obj = document()
    obj["source_sha256"] = "b" * 64
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(AudioMotionError):
        cues.load_motion_cues("project", HASH)


def test_missing_document_returns_none(project):
    assert cues.load_motion_cues("project", HASH) is None


@pytest.mark.parametrize("fps,expected", [(12, 12), (24, 24), (30, 30), (60, 60)])
def test_cue_seconds_are_independent_of_fps(fps, expected):
    assert cues.cue_frame_index(1, fps, 3000) == expected


def test_frame_projection_clamps_and_rejects_nan():
    assert cues.cue_frame_index(100, 24, 50) == 49
    with pytest.raises(AudioMotionError):
        cues.cue_frame_index(float("nan"), 24, 300)
