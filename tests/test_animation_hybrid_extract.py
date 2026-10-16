from __future__ import annotations
import pytest
from morphorum.animation_hybrid_extract import validate_extraction
from morphorum.animation_hybrid_source import HybridSourceError

def test_extract_normal_range():
    result=validate_extraction(0, 3, 12, 10)
    assert result["estimated_frames"]==36

@pytest.mark.parametrize("start,end,fps,duration", [
    (-1,1,12,2),(1,1,12,2),(0,4,12,3),(0,10,121,10),(0,100,120,100),
    (0,float("nan"),12,10),
])
def test_extract_bounds(start,end,fps,duration):
    with pytest.raises(HybridSourceError):
        validate_extraction(start,end,fps,duration)


def test_extraction_manifest_rejects_stale_video_after_replacement(tmp_path, monkeypatch):
    import json
    import morphorum.animation_hybrid_extract as extraction
    root = tmp_path / "assets" / "hybrid"
    frames = root / "frames"
    frames.mkdir(parents=True)
    video = root / "source.mp4"
    video.write_bytes(b"first upload")
    stat = video.stat()
    (frames / "frame_000001.png").write_bytes(b"source frame")
    (frames / "manifest.json").write_text(json.dumps({
        "source": "source.mp4", "frames": 1, "fps": 12,
        "filenames": ["frame_000001.png"],
        "source_mtime_ns": stat.st_mtime_ns,
        "source_size_bytes": stat.st_size,
        "extraction_id": "extract-v1",
    }))
    monkeypatch.setattr(extraction, "animation_project_directory", lambda _id: tmp_path)
    monkeypatch.setattr(extraction, "managed_video_path", lambda _id, _file: video)
    manager = extraction.HybridExtractionManager()
    assert manager.manifest("project")["extraction_id"] == "extract-v1"
    video.write_bytes(b"replacement video data")
    with pytest.raises(HybridSourceError, match="previous video"):
        manager.manifest("project")


def test_extraction_pins_ffmpeg_at_submission_even_if_settings_change(monkeypatch):
    import morphorum.animation_hybrid_extract as extraction

    class QueuedExecutor:
        def submit(self, *_args):
            return None

    monkeypatch.setattr(extraction, "_POOL", QueuedExecutor())
    monkeypatch.setattr(extraction, "probe_managed_video",
                        lambda _project, _filename: {"duration_seconds": 5})
    monkeypatch.setattr(extraction, "ffmpeg_executable", lambda: "/host/bin/ffmpeg-v1")
    manager = extraction.HybridExtractionManager()
    job = manager.start("project", "clip.mp4", 0, 1, 12)
    assert manager._binaries[job["id"]] == "/host/bin/ffmpeg-v1"
    monkeypatch.setattr(extraction, "ffmpeg_executable", lambda: "/host/bin/ffmpeg-v2")
    assert manager._binaries[job["id"]] == "/host/bin/ffmpeg-v1"
    manager.cancel("project", job["id"])
    manager._run(job["id"])
    assert job["id"] not in manager._binaries
    assert manager.status("project", job["id"])["status"] == "canceled"
