"""WebUI project-media inventory must recover good assets independently."""
from __future__ import annotations

import hashlib

from morphorum import imported_soundtrack, project_assets


def fixture_store(tmp_path, monkeypatch):
    monkeypatch.setattr(project_assets, "animation_project_directory", lambda project_id: tmp_path)
    monkeypatch.setattr(imported_soundtrack, "animation_project_directory", lambda project_id: tmp_path)


def test_missing_start_image_and_saved_audio_layer_are_reported(tmp_path, monkeypatch):
    fixture_store(tmp_path, monkeypatch)
    missing_sha = "a" * 64
    project = {
        "animation": {"source_image": "assets/source.png"},
        "motion_lab": {"layers": [{"type": "audio", "sha256": missing_sha}]},
    }
    result = project_assets.catalog_with_warnings("example", project)
    assert result["schema_version"] == 1
    assert result["assets"] == []
    assert any("start image is missing" in issue for issue in result["warnings"])
    assert any("missing WAV" in issue for issue in result["warnings"])


def test_broken_soundtrack_metadata_does_not_hide_valid_wav(tmp_path, monkeypatch):
    fixture_store(tmp_path, monkeypatch)
    wav_bytes = b"RIFF" + b"example-project-wav"
    sha = hashlib.sha256(wav_bytes).hexdigest()
    wav_dir = tmp_path / "motion_lab_audio"
    wav_dir.mkdir()
    (wav_dir / (sha + ".wav")).write_bytes(wav_bytes)
    imported_dir = tmp_path / "imported_soundtrack"
    imported_dir.mkdir()
    (imported_dir / "attachment.json").write_text("bad-json", encoding="utf-8")
    result = project_assets.catalog_with_warnings(
        "example", {"animation": {}, "motion_lab": {"layers": []}},
    )
    assert [entry["kind"] for entry in result["assets"]] == ["motion_lab_wav"]
    assert result["assets"][0]["sha256"] == sha
    assert any("soundtrack" in issue for issue in result["warnings"])
    assert all(str(tmp_path) not in issue for issue in result["warnings"])


def test_unreadable_source_does_not_hide_valid_soundtrack(tmp_path, monkeypatch):
    fixture_store(tmp_path, monkeypatch)
    source = tmp_path / "assets"
    source.mkdir()
    (source / "source.png").write_bytes(b"")  # cannot produce a valid asset descriptor
    song = b"ID3" + b"music" * 8
    stored = imported_soundtrack.store_soundtrack(
        "example", song, filename="song.mp3", offset_seconds=1.25,
    )
    result = project_assets.catalog_with_warnings(
        "example", {"animation": {"source_image": "assets/source.png"},
                    "motion_lab": {"layers": []}},
    )
    assert [entry["kind"] for entry in result["assets"]] == ["soundtrack"]
    assert result["assets"][0]["sha256"] == stored["sha256"]
    assert any("start image" in issue for issue in result["warnings"])


def test_corrupt_wav_does_not_hide_source_image(tmp_path, monkeypatch):
    fixture_store(tmp_path, monkeypatch)
    source = tmp_path / "assets"
    source.mkdir()
    (source / "source.png").write_bytes(b"png-data")
    audio = tmp_path / "motion_lab_audio"
    audio.mkdir()
    broken_sha = "b" * 64
    (audio / (broken_sha + ".wav")).write_bytes(b"tampered")
    result = project_assets.catalog_with_warnings(
        "example", {"animation": {"source_image": "assets/source.png"},
                    "motion_lab": {"layers": [{"type": "audio", "sha256": broken_sha}]}},
    )
    assert [entry["kind"] for entry in result["assets"]] == ["source_image"]
    assert any("damaged" in issue for issue in result["warnings"])
    assert any("missing WAV" in issue for issue in result["warnings"])
