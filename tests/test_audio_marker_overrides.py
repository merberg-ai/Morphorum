"""DA3.2 durable audio marker override regression coverage."""
import json
import pytest

from morphorum import audio_marker_overrides as markers
from morphorum.audio_motion import AudioMotionError

HASH = "a" * 64


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(markers, "animation_project_directory", lambda _: tmp_path)
    folder = tmp_path / "motion_lab_audio"
    folder.mkdir()
    (folder / (HASH + ".wav")).write_bytes(b"RIFF")
    return tmp_path


def test_round_trip_preserves_corrected_markers(project):
    source = {"source_sha256": HASH, "duration_seconds": 8.0, "events": [
        {"id": "snare-1", "kind": "snare", "time_seconds": 2.125, "enabled": False},
        {"id": "manual-1", "kind": "kick", "time_seconds": 0.25, "enabled": True},
    ]}
    saved = markers.write_marker_overrides("demo", source)
    assert saved["events"][0]["id"] == "manual-1"
    assert markers.read_marker_overrides("demo", HASH) == saved
    assert saved["schema_version"] == 1


@pytest.mark.parametrize("changes", [
    {"source_sha256": "../bad"},
    {"source_sha256": "b" * 64},
    {"events": [{"id": "x", "kind": "kick", "enabled": True, "time_seconds": 9}]},
    {"events": [{"id": "x", "kind": "unknown", "enabled": True, "time_seconds": 1}]},
    {"events": [{"id": "x", "kind": "kick", "enabled": 1, "time_seconds": 1}]},
    {"events": [{"id": "x", "kind": "kick", "enabled": True, "time_seconds": float("nan")}]},
])
def test_reject_invalid_override(project, changes):
    source = {"source_sha256": HASH, "duration_seconds": 8.0, "events": []}
    source.update(changes)
    with pytest.raises(AudioMotionError):
        markers.write_marker_overrides("demo", source)


def test_missing_sidecar_returns_none(project):
    assert markers.read_marker_overrides("demo", HASH) is None


def test_invalid_saved_source_is_not_accepted(project):
    dest = project / "motion_lab_audio" / (HASH + ".markers.json")
    dest.write_text(json.dumps({"source_sha256": "b" * 64, "events": []}))
    with pytest.raises(AudioMotionError):
        markers.read_marker_overrides("demo", HASH)
