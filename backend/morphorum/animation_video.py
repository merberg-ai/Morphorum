"""B5.4: FFmpeg video export from completed animation PNG sequences.

Export is independent of generation and never loads an inference model. Each
completed render has a frozen project/seed manifest and a sequential PNG set.
"""
from __future__ import annotations

import hashlib
import json
import math
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
from .animation_projects import animation_project_directory
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


def _render_audio_source(project_id: str, manifest: dict[str, Any]) -> Path | None:
    """Select Motion Lab WAV pinned by the completed render's frozen layers."""
    layers = ((manifest.get("project") or {}).get("motion_lab") or {}).get("layers") or []
    hashes = {str(layer.get("sha256") or "") for layer in layers
              if isinstance(layer, dict) and layer.get("type") == "audio"
              and layer.get("enabled", True)}
    if not hashes:
        return None
    if len(hashes) != 1:
        raise VideoExportError(
            "Multiple audio sources in this render. A single soundtrack is required for export.")
    digest = hashes.pop()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise VideoExportError("Render soundtrack hash is invalid.")
    source = animation_project_directory(project_id) / "motion_lab_audio" / (digest + ".wav")
    if not source.is_file():
        raise VideoExportError("Analyzed WAV for this render is missing. Restore the project WAV.")
    return source


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VideoExportError(f"Could not read frozen soundtrack: {exc}") from exc
    return digest.hexdigest()


def _imported_render_audio_source(
    project_id: str,
    render_id: str,
    manifest: dict[str, Any],
) -> tuple[Path, float] | None:
    snapshot = (manifest.get("project") or {}).get("_imported_soundtrack_snapshot")
    if snapshot is None:
        return None
    if not isinstance(snapshot, dict):
        raise VideoExportError("Imported soundtrack snapshot is invalid.")
    fmt = str(snapshot.get("format") or "")
    if fmt not in {"wav", "mp3", "ogg", "flac"}:
        raise VideoExportError("Imported soundtrack format is invalid.")
    digest = str(snapshot.get("sha256") or "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise VideoExportError("Imported soundtrack checksum is invalid.")
    render_filename = str(snapshot.get("render_filename") or "")
    expected_filename = "imported-soundtrack." + fmt
    if render_filename != expected_filename:
        raise VideoExportError("Imported soundtrack render filename is invalid.")
    try:
        offset = float(snapshot.get("offset_seconds", 0.0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise VideoExportError("Imported soundtrack offset is invalid.") from exc
    if not math.isfinite(offset) or abs(offset) > 30:
        raise VideoExportError("Imported soundtrack offset must be within -30 and +30 seconds.")
    source = _render_dir(project_id, render_id) / render_filename
    if not source.is_file():
        raise VideoExportError(
            "Frozen imported soundtrack is missing from this render. Re-render after reattaching audio."
        )
    if _sha256_file(source) != digest:
        raise VideoExportError(
            "Frozen imported soundtrack checksum does not match the render manifest."
        )
    return source, offset


def _render_audio_plan(
    project_id: str,
    render_id: str,
    manifest: dict[str, Any],
) -> tuple[Path | None, float, str | None]:
    motion_lab = _render_audio_source(project_id, manifest)
    imported = _imported_render_audio_source(project_id, render_id, manifest)
    if motion_lab is not None and imported is not None:
        raise VideoExportError(
            "This render contains both Motion Lab audio and an imported soundtrack. "
            "Remove one audio source and render again before exporting video."
        )
    if imported is not None:
        return imported[0], imported[1], "imported_soundtrack"
    if motion_lab is not None:
        return motion_lab, 0.0, "motion_lab"
    return None, 0.0, None


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
    audio_path: Path | None = None,
    audio_offset_seconds: float = 0.0,
) -> list[str]:
    # x264 and VP9 yuv420p need even dimensions. The adjustment is applied
    # in FFmpeg, leaving original PNGs untouched.
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-y", "-framerate", str(fps), "-start_number", "0",
        "-i", str(input_pattern),
    ]
    if audio_path is not None:
        command += ["-i", str(audio_path)]
    command += [
        "-map", "0:v:0",
        "-frames:v", str(frame_count),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt", "yuv420p",
    ]
    if audio_path is not None:
        try:
            offset = float(audio_offset_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise VideoExportError("Audio offset must be a finite number.") from exc
        if not math.isfinite(offset) or abs(offset) > 30:
            raise VideoExportError("Audio offset must be within -30 and +30 seconds.")
        if offset > 1e-9:
            audio_filter = f"atrim=start={offset:.6f},asetpts=PTS-STARTPTS,apad"
        elif offset < -1e-9:
            audio_filter = f"adelay={int(round(-offset * 1000))}:all=1,apad"
        else:
            audio_filter = "apad"
        command += ["-map", "1:a:0", "-af", audio_filter,
                    "-t", f"{frame_count / fps:.6f}"]
    else:
        command += ["-an"]
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
    if audio_path is not None:
        command += ["-c:a", "aac" if format == "mp4" else "libopus",
                    "-b:a", "192k" if format == "mp4" else "128k"]
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
    audio_included: bool = False
    audio_source: str | None = None
    audio_offset_seconds: float = 0.0
    created_at: str = field(default_factory=_timestamp)
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued video export"
    error: str | None = None
    bytes: int | None = None
    sha256: str | None = None
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
        soundtrack, audio_offset, audio_source = _render_audio_plan(
            project_id, render_id, manifest
        )
        if soundtrack is not None:
            original_fps = float((manifest.get("project") or {}).get("animation", {}).get("fps") or 0)
            if abs(fps - original_fps) > 1e-6:
                raise VideoExportError(
                    "Audio-synchronized video must use the original render FPS. "
                    "Clear the export FPS override to preserve soundtrack timing.")
        output = _export_path(project_id, render_id, fmt, quality, fps)
        job = VideoExportJob(
            id="video-" + uuid.uuid4().hex[:12],
            project_id=project_id, render_id=render_id,
            format=fmt, quality=quality, fps=fps, total_frames=count,
            audio_included=soundtrack is not None,
            audio_source=audio_source,
            audio_offset_seconds=audio_offset,
        )
        with self._lock:
            if output in self._active_outputs:
                raise VideoExportError("This video variant is already being exported.")
            self._active_outputs.add(output)
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run, args=(job, ffmpeg, output, soundtrack, audio_offset),
            daemon=True, name=f"morphorum-{job.id}",
        )
        thread.start()
        emit_console("info", "animation",
                     f"Queued {fmt.upper()} video export {job.id} from {render_id} ({count} frames).")
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

    @staticmethod
    def checksum(path: Path) -> str:
        """Digest for authenticated download; support older exports without metadata."""
        record = _export_record_path(path)
        try:
            payload = json.loads(record.read_text(encoding="utf-8"))
            value = payload.get("sha256")
            if (isinstance(value, str)
                    and re.fullmatch(r"[0-9a-f]{64}", value)
                    and payload.get("bytes") == path.stat().st_size):
                return value
        except (OSError, ValueError, TypeError):
            pass
        return _sha256_file(path)

    def _run(
        self,
        job: VideoExportJob,
        ffmpeg: str,
        output: Path,
        soundtrack: Path | None = None,
        audio_offset_seconds: float = 0.0,
    ) -> None:
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
                quality=job.quality, fps=job.fps, audio_path=soundtrack,
                audio_offset_seconds=audio_offset_seconds,
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
                    value = value.strip()
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
                job.sha256 = _sha256_file(output)
                job.message = f"{job.format.upper()} export ready ({job.bytes} bytes)"
                job.completed_at = _timestamp()
                _atomic_json(record_path, job.public())
            emit_console("info", "animation",
                         f"Video export {job.id} complete: {output.name}, {job.bytes} bytes.")
        except (OSError, ValueError, VideoExportError, subprocess.SubprocessError) as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.message = "FFmpeg export failed"
                job.completed_at = _timestamp()
                _atomic_json(record_path, job.public())
            emit_console("error", "animation", f"Video export {job.id} failed: {exc}")
        finally:
            temp.unlink(missing_ok=True)
            with self._lock:
                self._active_outputs.discard(output)


video_export_manager = VideoExportManager()
