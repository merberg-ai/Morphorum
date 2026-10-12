from __future__ import annotations

import hashlib
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


def test_ml41_frozen_audio_soundtrack_muxed_into_mp4_and_webm(tmp_path, monkeypatch):
    project_id, render_id, root = _render_fixture(tmp_path, monkeypatch)
    payload = json.loads((root / "render-manifest.json").read_text())
    digest = "a" * 64
    payload["project"]["motion_lab"] = {"layers": [{
        "type": "audio", "enabled": True, "sha256": digest,
    }]}
    (root / "render-manifest.json").write_text(json.dumps(payload))
    sound = tmp_path / "project" / "motion_lab_audio"
    sound.mkdir(parents=True)
    wav = sound / (digest + ".wav")
    wav.write_bytes(b"test-wav")
    monkeypatch.setattr(video, "animation_project_directory", lambda _p: sound.parent)
    assert video._render_audio_source(project_id, payload) == wav
    for fmt, codec in (("mp4", "aac"), ("webm", "libopus")):
        cmd = video._command(
            "ffmpeg", input_pattern=Path("frame_%06d.png"),
            destination=Path("output." + fmt), frame_count=36,
            format=fmt, quality="balanced", fps=12, audio_path=wav,
        )
        assert cmd[cmd.index("-c:a") + 1] == codec
        assert cmd[cmd.index("-i") + 1] == "frame_%06d.png"
        assert cmd[cmd.index("-i", cmd.index("-i") + 1) + 1] == str(wav)
        assert cmd[cmd.index("-t") + 1] == "3.000000"
        assert "-an" not in cmd
        assert cmd[cmd.index("-map") + 1] == "0:v:0"
        assert "1:a:0" in cmd
    wav.unlink()
    with pytest.raises(video.VideoExportError, match="missing"):
        video._render_audio_source(project_id, payload)


def test_ml41_missing_or_multiple_audio_sources_never_silently_mux_wrong_track(tmp_path, monkeypatch):
    project_id, render_id, root = _render_fixture(tmp_path, monkeypatch)
    payload = json.loads((root / "render-manifest.json").read_text())
    assert video._render_audio_source(project_id, payload) is None
    payload["project"]["motion_lab"] = {"layers": [
        {"type": "audio", "sha256": "a" * 64},
        {"type": "audio", "sha256": "b" * 64},
    ]}
    with pytest.raises(video.VideoExportError, match="Multiple audio"):
        video._render_audio_source(project_id, payload)


def test_ml41_real_ffmpeg_soundtrack_export_when_available(tmp_path):
    import math
    import shutil
    import struct
    import subprocess
    import wave
    from PIL import Image

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and ffprobe not installed on this runner")
    folder = tmp_path / "frames"
    folder.mkdir()
    for frame in range(12):
        Image.new("RGB", (32, 32), (frame * 12, 20, 40)).save(
            folder / f"frame_{frame:06d}.png")
    wav = tmp_path / "beat.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(12000)
        out.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(
            2 * math.pi * 200 * n / 12000))) for n in range(12000)))
    for fmt in ("mp4", "webm"):
        destination = tmp_path / ("soundtrack." + fmt)
        command = video._command(
            ffmpeg, input_pattern=folder / "frame_%06d.png",
            destination=destination, frame_count=12, format=fmt,
            quality="compact", fps=12, audio_path=wav)
        run = subprocess.run(command, capture_output=True, text=True, timeout=45)
        assert run.returncode == 0, run.stderr
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", str(destination)],
            capture_output=True, text=True, timeout=15)
        assert probe.returncode == 0, probe.stderr
        streams = probe.stdout.split()
        assert "video" in streams and "audio" in streams


def test_dmi3_imported_soundtrack_uses_frozen_render_copy_and_preview_offset(
    tmp_path: Path, monkeypatch,
) -> None:
    project_id, render_id, root = _render_fixture(tmp_path, monkeypatch, frames=24)
    payload = json.loads((root / "render-manifest.json").read_text())
    data = b"ID3" + b"frozen-track" * 12
    digest = hashlib.sha256(data).hexdigest()
    payload["project"]["_imported_soundtrack_snapshot"] = {
        "schema_version": 1,
        "sha256": digest,
        "format": "mp3",
        "filename": "song.mp3",
        "bytes": len(data),
        "offset_seconds": 1.25,
        "render_filename": "imported-soundtrack.mp3",
    }
    (root / "render-manifest.json").write_text(json.dumps(payload))
    frozen = root / "imported-soundtrack.mp3"
    frozen.write_bytes(data)

    path, offset, source = video._render_audio_plan(project_id, render_id, payload)
    assert path == frozen
    assert offset == pytest.approx(1.25)
    assert source == "imported_soundtrack"

    positive = video._command(
        "ffmpeg", input_pattern=Path("frame_%06d.png"),
        destination=Path("positive.mp4"), frame_count=24,
        format="mp4", quality="balanced", fps=12, audio_path=frozen,
        audio_offset_seconds=1.25,
    )
    assert positive[positive.index("-af") + 1] == (
        "atrim=start=1.250000,asetpts=PTS-STARTPTS,apad"
    )

    negative = video._command(
        "ffmpeg", input_pattern=Path("frame_%06d.png"),
        destination=Path("negative.mp4"), frame_count=24,
        format="mp4", quality="balanced", fps=12, audio_path=frozen,
        audio_offset_seconds=-0.75,
    )
    assert negative[negative.index("-af") + 1] == "adelay=750:all=1,apad"


def test_dmi3_video_export_refuses_imported_and_motion_lab_audio_conflict(
    tmp_path: Path, monkeypatch,
) -> None:
    project_id, render_id, root = _render_fixture(tmp_path, monkeypatch)
    payload = json.loads((root / "render-manifest.json").read_text())
    motion_digest = "a" * 64
    payload["project"]["motion_lab"] = {
        "layers": [{"type": "audio", "enabled": True, "sha256": motion_digest}]
    }
    project_root = tmp_path / "project"
    motion_dir = project_root / "motion_lab_audio"
    motion_dir.mkdir(parents=True)
    (motion_dir / (motion_digest + ".wav")).write_bytes(b"motion")
    monkeypatch.setattr(video, "animation_project_directory", lambda _p: project_root)

    imported = b"OggS" + b"imported" * 8
    imported_digest = hashlib.sha256(imported).hexdigest()
    payload["project"]["_imported_soundtrack_snapshot"] = {
        "schema_version": 1,
        "sha256": imported_digest,
        "format": "ogg",
        "filename": "imported.ogg",
        "bytes": len(imported),
        "offset_seconds": 0,
        "render_filename": "imported-soundtrack.ogg",
    }
    (root / "imported-soundtrack.ogg").write_bytes(imported)
    with pytest.raises(video.VideoExportError, match="both Motion Lab audio"):
        video._render_audio_plan(project_id, render_id, payload)
