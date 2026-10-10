"""B6.3.1 extraction mapping and frozen source non-regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

import morphorum.animation_hybrid_render as hybrid
import morphorum.animation_hybrid_source as hybrid_source
from morphorum.animation_hybrid_render import (
    HybridRenderError, freeze_hybrid_source, frozen_hybrid_frame,
    normalize_hybrid_settings, source_index,
)


def _sequence(tmp_path: Path, monkeypatch, count: int = 4, fps: float = 12) -> Path:
    root = tmp_path / "project" / "assets" / "hybrid" / "frames"
    root.mkdir(parents=True)
    names = []
    for i in range(1, count + 1):
        filename = f"frame_{i:06d}.png"
        Image.new("RGB", (24, 24), (i * 25, 0, 0)).save(root / filename)
        names.append(filename)
    (root / "manifest.json").write_text(json.dumps({
        "source": "source.mp4", "frames": count,
        "fps": fps, "filenames": names, "start": 0, "end": count / fps,
    }), encoding="utf-8")
    monkeypatch.setattr(hybrid, "animation_project_directory", lambda _id: tmp_path / "project")
    monkeypatch.setattr(hybrid_source, "animation_project_directory", lambda _id: tmp_path / "project")
    return root


def _project(**settings) -> dict:
    return {
        "id": "hybrid-test",
        "animation": {"max_frames": 8, "fps": 24.0},
        "hybrid": {"enabled": True, "offset_frames": 0, **settings},
    }


def test_hybrid_defaults_are_disabled_and_offset_validated():
    assert normalize_hybrid_settings(None) == {
        "enabled": False, "offset_frames": 0, "end_policy": "hold-last",
    }
    with pytest.raises(HybridRenderError):
        normalize_hybrid_settings({"enabled": "false"})
    with pytest.raises(HybridRenderError):
        normalize_hybrid_settings({"enabled": True, "offset_frames": -1})


def test_hybrid_frame_mapping_uses_timeline_seconds_and_explicit_hold_last():
    assert [source_index(n, 24, 12, 4) for n in range(9)] == [
        1, 2, 2, 3, 3, 4, 4, 4, 4,
    ]
    assert source_index(0, 24, 12, 4, 1) == 2
    assert source_index(100, 24, 12, 4) == 4


def test_hybrid_snapshot_freezes_selected_frames_for_resume(tmp_path, monkeypatch):
    root = _sequence(tmp_path, monkeypatch)
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    snapshot = freeze_hybrid_source(_project(), render_dir)
    assert snapshot and snapshot["mode"] == "anchor-init"
    assert len(snapshot["frame_indices"]) == 8
    assert len(list((render_dir / "hybrid-source").glob("frame_*.png"))) == 4
    original = frozen_hybrid_frame(snapshot, render_dir, 0)
    assert original and original[1]["source_frame"] == 1
    with Image.open(original[0]) as im:
        assert im.getpixel((0, 0)) == (25, 0, 0)
    Image.new("RGB", (24, 24), "blue").save(root / "frame_000001.png")
    with Image.open(frozen_hybrid_frame(snapshot, render_dir, 0)[0]) as im:
        assert im.getpixel((0, 0)) == (25, 0, 0)


def test_hybrid_snapshot_rejects_unsafe_names_and_out_of_range_offset(tmp_path, monkeypatch):
    root = _sequence(tmp_path, monkeypatch)
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    payload["filenames"][0] = "../frame_000001.png"
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(HybridRenderError, match="unsafe"):
        freeze_hybrid_source(_project(), tmp_path)
    payload["filenames"][0] = "frame_000001.png"
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(HybridRenderError, match="offset exceeds"):
        freeze_hybrid_source(_project(offset_frames=4), tmp_path)


def test_hybrid_render_requires_extraction_and_rejects_missing_frozen_file(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid, "animation_project_directory", lambda _id: tmp_path / "missing")
    with pytest.raises(HybridRenderError, match="extract"):
        freeze_hybrid_source(_project(), tmp_path)
    root = _sequence(tmp_path, monkeypatch)
    snap = freeze_hybrid_source(_project(), tmp_path)
    (tmp_path / "hybrid-source" / "frame_000001.png").unlink()
    with pytest.raises(HybridRenderError, match="missing"):
        frozen_hybrid_frame(snap, tmp_path, 0)


def test_hybrid_source_revision_guard_detects_replaced_upload(tmp_path, monkeypatch):
    root = _sequence(tmp_path, monkeypatch)
    original_video = root.parent / "source.mp4"
    original_video.write_bytes(b"old-source")
    stat = original_video.stat()
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    payload["source_mtime_ns"] = stat.st_mtime_ns
    payload["source_size_bytes"] = stat.st_size
    manifest_path.write_text(json.dumps(payload))
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    freeze_hybrid_source(_project(), render_dir)
    original_video.write_bytes(b"new-source-is-different")
    with pytest.raises(HybridRenderError, match="changed"):
        freeze_hybrid_source(_project(), tmp_path / "next")
