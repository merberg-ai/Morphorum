from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import morphorum.animation_video as video
from morphorum.app import app


def _render_fixture(tmp_path: Path, monkeypatch, *, frames=3, status="completed"):
    root = tmp_path / "render"
    frame_dir = root / "frames"
    frame_dir.mkdir(parents=True)
    project_id, render_id = "b54-project", "anim-20261008-000000-abcdef"
    payload = {
        "id": render_id, "project_id": project_id, "status": status,
        "total_frames": frames,
        "project": {"animation": {"fps": 12}},
    }
    (root / "render-manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    for index in range(frames):
        (frame_dir / f"frame_{index:06d}.png").write_bytes(b"png-data")
    monkeypatch.setattr(video, "_render_dir", lambda p, r: root)
    return project_id, render_id, root


def test_b54_video_encoder_command_supports_both_formats() -> None:
    mp4 = video._command(
        "ffmpeg", input_pattern=Path("frames/frame_%06d.png"),
        destination=Path("animation.mp4.part"), frame_count=20,
        format="mp4", quality="balanced", fps=24,
    )
    webm = video._command(
        "ffmpeg", input_pattern=Path("frames/frame_%06d.png"),
        destination=Path("animation.webm.part"), frame_count=20,
        format="webm", quality="high", fps=12,
    )
    assert mp4[:2] == ["ffmpeg", "-hide_banner"]
    assert mp4[mp4.index("-start_number") + 1] == "0"
    assert mp4[mp4.index("-frames:v") + 1] == "20"
    assert mp4[mp4.index("-c:v") + 1] == "libx264"
    assert mp4[mp4.index("-crf") + 1] == "23"
    assert "+faststart" in mp4
    assert "-progress" in mp4 and "pipe:1" in mp4
    assert "scale=trunc(iw/2)*2:trunc(ih/2)*2" in mp4
    assert webm[webm.index("-c:v") + 1] == "libvpx-vp9"
    assert webm[webm.index("-crf") + 1] == "24"
    assert "-an" in webm and "yuv420p" in webm
    assert not any("shell" in arg for arg in mp4)


def test_b54_export_rejects_incomplete_render_and_missing_frames(
    tmp_path: Path, monkeypatch,
) -> None:
    project, render, root = _render_fixture(tmp_path, monkeypatch, status="cancelled")
    manager = video.VideoExportManager()
    with pytest.raises(video.VideoExportError, match="Finish or resume"):
        manager.start(project, render)
    payload = json.loads((root / "render-manifest.json").read_text())
    payload["status"] = "completed"
    (root / "render-manifest.json").write_text(json.dumps(payload))
    (root / "frames" / "frame_000001.png").unlink()
    with pytest.raises(video.VideoExportError, match="frame 1 is missing"):
        manager.start(project, render)
    assert not list(root.glob("exports/*"))


def test_b54_export_validates_identity_fps_codec_quality_and_install(
    tmp_path: Path, monkeypatch,
) -> None:
    project, render, _ = _render_fixture(tmp_path, monkeypatch)
    manager = video.VideoExportManager()
    with pytest.raises(video.VideoExportError, match="Invalid project"):
        manager.start("../escape", render)
    with pytest.raises(video.VideoExportError, match="format must"):
        manager.start(project, render, format="avi")
    with pytest.raises(video.VideoExportError, match="quality must"):
        manager.start(project, render, quality="extra")
    with pytest.raises(video.VideoExportError, match="FPS must"):
        manager.start(project, render, fps=121)
    monkeypatch.setattr(video, "ffmpeg_executable", lambda: None)
    assert not video.export_availability()["available"]
    with pytest.raises(video.VideoExportError, match="FFmpeg not found"):
        manager.start(project, render)


def test_b54_export_job_persists_video_reloads_and_serves_completed_file(
    tmp_path: Path, monkeypatch,
) -> None:
    project, render, root = _render_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(video, "ffmpeg_executable", lambda: "ffmpeg")

    calls = []

    class FakeEncoder:
        def __init__(self, argv, **options):
            calls.append((argv, options))
            assert options.get("stdin") is not None
            assert options.get("shell") is None
            Path(argv[-1]).write_bytes(b"encoded-fake-mp4")
            self.stdout = iter(["frame=1\n", "progress=continue\n", "frame=3\n", "progress=end\n"])
        def wait(self):
            return 0

    monkeypatch.setattr(video.subprocess, "Popen", FakeEncoder)
    manager = video.VideoExportManager()
    started = manager.start(project, render)
    assert started["format"] == "mp4"
    assert started["fps"] == 12  # Original render manifest FPS.
    assert started["status"] in {"queued", "encoding", "completed"}
    for _ in range(200):
        job = manager.get(started["id"])
        if job["status"] in {"failed", "completed"}:
            break
        time.sleep(0.01)
    assert job["status"] == "completed", job
    assert job["progress"] == 1.0
    assert job["bytes"] == len(b"encoded-fake-mp4")
    assert len(calls) == 1
    output = manager.file(project, render, "mp4", "balanced", 12)
    assert output.read_bytes() == b"encoded-fake-mp4"
    assert not (root / "exports" / (output.name + ".part")).exists()
    assert len(manager.list(project, render)) == 1
    # Simulate server restart: persistent records must be readable.
    restarted = video.VideoExportManager()
    history = restarted.list(project, render)
    assert history[0]["status"] == "completed"
    assert history[0]["url"].endswith("/video/mp4/balanced/12")


def test_b54_video_api_status_and_playback_headers(tmp_path: Path, monkeypatch) -> None:
    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"mp4")
    monkeypatch.setattr(
        video.video_export_manager, "available",
        lambda: {"available": True, "formats": ["mp4", "webm"], "qualities": ["balanced"]},
    )
    monkeypatch.setattr(
        video.video_export_manager, "start",
        lambda project_id, render_id, **options: {
            "id": "video-123", "status": "queued", "project_id": project_id,
            "render_id": render_id, **options,
        },
    )
    monkeypatch.setattr(
        video.video_export_manager, "get",
        lambda job_id: {"id": job_id, "status": "completed"},
    )
    monkeypatch.setattr(
        video.video_export_manager, "list",
        lambda project_id, render_id: [{"status": "completed", "format": "mp4"}],
    )
    monkeypatch.setattr(video.video_export_manager, "file", lambda *_args: fake_file)
    with TestClient(app) as client:
        availability = client.get("/api/animation/video/availability")
        assert availability.status_code == 200
        assert availability.json()["available"] is True
        queued = client.post(
            "/api/animation/renders/proj/render/video",
            json={"format": "webm", "quality": "high", "fps": 30},
        )
        assert queued.status_code == 202
        assert queued.json()["format"] == "webm"
        assert queued.json()["fps"] == 30
        assert client.get("/api/animation/video/jobs/video-123").status_code == 200
        assert client.get("/api/animation/renders/proj/render/videos").json()["exports"]
        download = client.get("/api/animation/renders/proj/render/video/mp4/balanced/12")
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]
        inline = client.get("/api/animation/renders/proj/render/video/mp4/balanced/12?inline=true")
        assert inline.status_code == 200
        assert "inline" in inline.headers["content-disposition"]


def test_b54_legacy_2d_and_3d_video_use_original_pngs_only(
    tmp_path: Path, monkeypatch,
) -> None:
    project, render, root = _render_fixture(tmp_path, monkeypatch, frames=4)
    payload = json.loads((root / "render-manifest.json").read_text())
    for mode in ("2d", "3d"):
        payload["project"]["animation"]["mode"] = mode
        (root / "render-manifest.json").write_text(json.dumps(payload))
        checked = video._read_manifest(project, render)
        assert video._validate_frames(project, render, checked) == 4
        assert video._validate_options(checked, format="webm", quality="compact", fps=None) == ("webm", "compact", 12)
    assert not (root / "exports").exists()  # No render triggered in this test.
