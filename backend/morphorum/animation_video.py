"""B5.4: FFmpeg video export from completed animation PNG sequences.

Export is independent of generation and never loads an inference model. Each
completed render has a frozen project/seed manifest and a sequential PNG set.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .animation_render import _render_dir
from .console import emit_console

FORMATS = {"mp4", "webm"}
QUALITIES = {"high", "balanced", "compact"}
MAX_FPS = 120
_VALID_ID = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


class VideoExportError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validated_id(value: str) -> str:
    if not isinstance(value, str) or not _VALID_ID.fullmatch(value):
        raise VideoExportError("Invalid project or render identifier.")
    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def ffmpeg_executable() -> str | None:
    configured = os.environ.get("MORPHORUM_FFMPEG", "").strip()
    return shutil.which(configured) if configured else shutil.which("ffmpeg")


def export_availability() -> dict[str, Any]:
    executable = ffmpeg_executable()
    return {
        "available": executable is not None,
        "executable": executable,
        "formats": ["mp4", "webm"],
        "qualities": ["high", "balanced", "compact"],
        "message": (
            "FFmpeg detected. Existing PNG frames can be exported without diffusion."
            if executable else
            "FFmpeg not found. Install FFmpeg on the Morphorum host and add it to "
            "PATH, or set MORPHORUM_FFMPEG to the full ffmpeg executable path."
        ),
    }


def _read_manifest(project_id: str, render_id: str) -> dict[str, Any]:
    path = _render_dir(_validated_id(project_id), _validated_id(render_id)) / "render-manifest.json"
    if not path.is_file():
        raise VideoExportError("Animation render manifest not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VideoExportError(f"Cannot read animation render manifest: {exc}") from exc
    if payload.get("project_id") != project_id or payload.get("id") != render_id:
        raise VideoExportError("Animation manifest identity does not match the selected render.")
    return payload


def _validate_frames(project_id: str, render_id: str, manifest: dict[str, Any]) -> int:
    if manifest.get("status") != "completed":
        raise VideoExportError("Finish or resume the animation render before exporting video.")
    count = int(manifest.get("total_frames") or 0)
    if count < 1 or count > 10_000:
        raise VideoExportError("Animation render frame count is invalid.")
    frames_dir = _render_dir(project_id, render_id) / "frames"
    missing = next(
        (i for i in range(count) if not (frames_dir / f"frame_{i:06d}.png").is_file()),
        None,
    )
    if missing is not None:
        raise VideoExportError(
            f"Animation PNG sequence is incomplete: frame {missing} is missing. "
            "Video export never substitutes or generates missing frames."
        )
    return count


def _validate_options(
    manifest: dict[str, Any], *,
    format: str,
    quality: str,
    fps: int | None,
) -> tuple[str, str, int]:
    format = str(format).lower().strip()
    quality = str(quality).lower().strip()
    if format not in FORMATS:
        raise VideoExportError("Video format must be mp4 or webm.")
    if quality not in QUALITIES:
        raise VideoExportError("Video quality must be high, balanced, or compact.")
    original_fps = manifest.get("project", {}).get("animation", {}).get("fps")
    try:
        chosen_fps = int(fps if fps is not None else original_fps)
    except (ValueError, TypeError, OverflowError) as exc:
        raise VideoExportError("Video FPS must be an integer from 1 to 120.") from exc
    if not 1 <= chosen_fps <= MAX_FPS:
        raise VideoExportError("Video FPS must be from 1 to 120.")
    return format, quality, chosen_fps


def _export_path(project_id: str, render_id: str, format: str, quality: str, fps: int) -> Path:
    return _render_dir(project_id, render_id) / "exports" / (
        f"animation-{fps}fps-{quality}.{format}"
    )


def _export_record_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".json")


def _command(
    ffmpeg: str, *,
    input_pattern: Path,
    destination: Path,
    frame_count: int,
    format: str,
    quality: str,
    fps: int,
) -> list[str]:
    # x264 and VP9 yuv420p need even dimensions. The adjustment is applied
    # in FFmpeg, leaving original PNGs untouched.
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-y", "-framerate", str(fps), "-start_number", "0",
        "-i", str(input_pattern),
        "-frames:v", str(frame_count),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-an", "-pix_fmt", "yuv420p",
    ]
    if format == "mp4":
        command += [
            "-c:v", "libx264", "-preset", "medium",
            "-crf", str({"high": 18, "balanced": 23, "compact": 28}[quality]),
            "-movflags", "+faststart",
            "-f", "mp4",
        ]
    else:
        command += [
            "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "4",
            "-b:v", "0",
            "-crf", str({"high": 24, "balanced": 32, "compact": 38}[quality]),
            "-f", "webm",
        ]
    # Write to .part, atomically rename on success. Explicit -f ensures
    # FFmpeg can encode despite the temporary file extension.
    return command + ["-progress", "pipe:1", str(destination)]


@dataclass
class VideoExportJob:
    id: str
    project_id: str
    render_id: str
    format: str
    quality: str
    fps: int
    total_frames: int
    created_at: str = field(default_factory=_timestamp)
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued video export"
    error: str | None = None
    bytes: int | None = None
    completed_at: str | None = None

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        if self.status == "completed":
            result["url"] = (
                f"/api/animation/renders/{self.project_id}/{self.render_id}/"
                f"video/{self.format}/{self.quality}/{self.fps}"
            )
        return result


class VideoExportManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, VideoExportJob] = {}
        self._active_outputs: set[Path] = set()

    def available(self) -> dict[str, Any]:
        return export_availability()

    def start(
        self, project_id: str, render_id: str, *,
        format: str = "mp4",
        quality: str = "balanced",
        fps: int | None = None,
    ) -> dict[str, Any]:
        manifest = _read_manifest(project_id, render_id)
        count = _validate_frames(project_id, render_id, manifest)
        fmt, quality, fps = _validate_options(
            manifest, format=format, quality=quality, fps=fps
        )
        ffmpeg = ffmpeg_executable()
        if ffmpeg is None:
            raise VideoExportError(export_availability()["message"])
        output = _export_path(project_id, render_id, fmt, quality, fps)
        job = VideoExportJob(
            id="video-" + uuid.uuid4().hex[:12],
            project_id=project_id, render_id=render_id,
            format=fmt, quality=quality, fps=fps, total_frames=count,
        )
        with self._lock:
            if output in self._active_outputs:
                raise VideoExportError("This video variant is already being exported.")
            self._active_outputs.add(output)
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run, args=(job, ffmpeg, output),
            daemon=True, name=f"morphorum-{job.id}",
        )
        thread.start()
        emit_console("info", "animation",
                     f"Queued B5.4 {fmt.upper()} export {job.id} from {render_id} ({count} PNG frames).")
        return job.public()

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise VideoExportError("Video export job not found.")
            return job.public()

    def list(self, project_id: str, render_id: str) -> list[dict[str, Any]]:
        # Always check render identity before inspecting any stored export.
        _read_manifest(project_id, render_id)
        export_dir = _render_dir(project_id, render_id) / "exports"
        records: list[dict[str, Any]] = []
        for path in sorted(export_dir.glob("animation-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("project_id") != project_id or payload.get("render_id") != render_id:
                    continue
                fmt, quality, fps = _validate_options(
                    _read_manifest(project_id, render_id),
                    format=payload["format"], quality=payload["quality"],
                    fps=payload["fps"],
                )
                output = _export_path(project_id, render_id, fmt, quality, fps)
                if payload.get("status") == "completed" and not output.is_file():
                    continue
                if payload.get("status") != "completed":
                    # Abandoned runs never pretend to be actively encoding.
                    payload["status"] = "interrupted"
                    payload["message"] = "Previous export interrupted; retry available"
                else:
                    payload["url"] = (
                        f"/api/animation/renders/{project_id}/{render_id}/"
                        f"video/{fmt}/{quality}/{fps}"
                    )
                records.append(payload)
            except (ValueError, TypeError, KeyError, OSError, VideoExportError):
                continue
        with self._lock:
            active = [
                item.public() for item in self._jobs.values()
                if item.project_id == project_id and item.render_id == render_id
                and item.status in {"queued", "encoding"}
            ]
        # Keep current process state authoritative over persisted records.
        by_variant = {
            (item["format"], item["quality"], item["fps"]): item for item in records
        }
        for item in active:
            by_variant[item["format"], item["quality"], item["fps"]] = item
        return sorted(by_variant.values(), key=lambda item: item.get("created_at", ""), reverse=True)

    def file(self, project_id: str, render_id: str, fmt: str, quality: str, fps: int) -> Path:
        manifest = _read_manifest(project_id, render_id)
        fmt, quality, fps = _validate_options(
            manifest, format=fmt, quality=quality, fps=fps,
        )
        output = _export_path(project_id, render_id, fmt, quality, fps)
        record = _export_record_path(output)
        if not output.is_file() or not record.is_file():
            raise VideoExportError("Requested video export is not available.")
        try:
            payload = json.loads(record.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise VideoExportError("Video export manifest cannot be read.") from exc
        if (payload.get("status") != "completed"
                or payload.get("project_id") != project_id
                or payload.get("render_id") != render_id):
            raise VideoExportError("Video export is not complete.")
        return output

    def _run(self, job: VideoExportJob, ffmpeg: str, output: Path) -> None:
        temp = output.with_name(output.name + ".part")
        log_path = output.with_name(output.name + ".ffmpeg.log")
        output.parent.mkdir(parents=True, exist_ok=True)
        record_path = _export_record_path(output)
        try:
            with self._lock:
                job.status = "encoding"
                job.message = f"Encoding {job.format.upper()} with FFmpeg"
                _atomic_json(record_path, job.public())
            command = _command(
                ffmpeg, input_pattern=output.parent.parent / "frames" / "frame_%06d.png",
                destination=temp, frame_count=job.total_frames, format=job.format,
                quality=job.quality, fps=job.fps,
            )
            # Only use argv, never a shell command. FFmpeg stderr is written
            # to a file, preventing the classic full-pipe deadlock.
            with log_path.open("wb") as error_log:
                process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=error_log, text=True, encoding="utf-8", errors="replace",
                )
                assert process.stdout is not None
                for line in process.stdout:
                    key, _, value = line.strip().partition("=")
                    if key == "frame" and value.isdecimal():
                        completed = min(job.total_frames, int(value))
                        with self._lock:
                            job.progress = min(0.99, completed / job.total_frames)
                            job.message = f"Encoding frame {completed}/{job.total_frames}"
                code = process.wait()
            if code != 0 or not temp.is_file() or temp.stat().st_size == 0:
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
                except OSError:
                    tail = ""
                raise VideoExportError(
                    f"FFmpeg exited with code {code}. {tail.strip() or 'Check FFmpeg codec support.'}"
                )
            temp.replace(output)
            with self._lock:
                job.status = "completed"
                job.progress = 1.0
                job.bytes = output.stat().st_size
                job.message = f"{job.format.upper()} export ready ({job.bytes} bytes)"
                job.completed_at = _timestamp()
                _atomic_json(record_path, job.public())
            emit_console("info", "animation",
                         f"B5.4 video export {job.id} complete: {output.name}, {job.bytes} bytes.")
        except (OSError, ValueError, VideoExportError, subprocess.SubprocessError) as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.message = "FFmpeg export failed"
                job.completed_at = _timestamp()
                _atomic_json(record_path, job.public())
            emit_console("error", "animation", f"B5.4 video export {job.id} failed: {exc}")
        finally:
            temp.unlink(missing_ok=True)
            with self._lock:
                self._active_outputs.discard(output)


video_export_manager = VideoExportManager()
