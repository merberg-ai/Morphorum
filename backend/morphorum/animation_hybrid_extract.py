"""B6.2 isolated FFmpeg extraction jobs; no generative rendering integration."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .animation_hybrid_source import HybridSourceError, managed_video_path, probe_managed_video
from .animation_projects import animation_project_directory
from .animation_video import ffmpeg_executable

MAX_EXTRACT_FRAMES = 1200
MAX_FPS = 120.0
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morphorum-hybrid")


def validate_extraction(start: Any, end: Any, fps: Any, duration: float) -> dict[str, Any]:
    try:
        start, end, fps = float(start), float(end), float(fps)
    except (TypeError, ValueError, OverflowError) as exc:
        raise HybridSourceError("Start, end and FPS must be numbers.") from exc
    if not all(math.isfinite(v) for v in (start, end, fps)):
        raise HybridSourceError("Extraction values must be finite.")
    if start < 0 or end <= start or end > duration + 0.01:
        raise HybridSourceError("Invalid extraction time range.")
    if fps < 1 or fps > MAX_FPS:
        raise HybridSourceError("Extraction FPS must be between 1 and 120.")
    count = math.ceil((end - start) * fps)
    if count < 1 or count > MAX_EXTRACT_FRAMES:
        raise HybridSourceError("Extraction is limited to 1200 frames per job.")
    return {"start": start, "end": end, "fps": fps, "estimated_frames": count}


class HybridExtractionManager:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def start(self, project_id: str, filename: str, start: Any, end: Any, fps: Any) -> dict[str, Any]:
        info = probe_managed_video(project_id, filename)
        params = validate_extraction(start, end, fps, info["duration_seconds"])
        with self._lock:
            if any(j["project_id"] == project_id and j["status"] in ("queued", "running") for j in self._jobs.values()):
                raise HybridSourceError("An extraction is already active for this project.")
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "project_id": project_id, "status": "queued",
                   "source_filename": filename, **params, "frames": 0, "error": None}
            self._jobs[job_id] = job
        _POOL.submit(self._run, job_id)
        return dict(job)

    def status(self, project_id: str, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["project_id"] != project_id:
                raise HybridSourceError("Unknown extraction job.")
            return dict(job)

    def cancel(self, project_id: str, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["project_id"] != project_id:
                raise HybridSourceError("Unknown extraction job.")
            if job["status"] in ("queued", "running"):
                job["status"] = "canceled"
                proc = self._processes.get(job_id)
                if proc:
                    proc.terminate()
            return dict(job)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] == "canceled":
                return
            job["status"] = "running"
            project_id = job["project_id"]
            filename = job["source_filename"]
            start, end, fps = job["start"], job["end"], job["fps"]
        root = animation_project_directory(project_id) / "assets" / "hybrid"
        staging = root / (".extract-" + job_id)
        destination = root / "frames"
        try:
            binary = ffmpeg_executable()
            if not binary:
                raise HybridSourceError("FFmpeg is unavailable.")
            staging.mkdir(parents=True, exist_ok=False)
            source = managed_video_path(project_id, filename)
            command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin",
                       "-ss", str(start), "-i", str(source), "-t", str(end - start),
                       "-vf", "fps=" + str(fps), "-frames:v", str(MAX_EXTRACT_FRAMES),
                       "-y", str(staging / "frame_%06d.png")]
            with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as proc:
                with self._lock:
                    self._processes[job_id] = proc
                    canceled = job["status"] == "canceled"
                if canceled:
                    proc.terminate()
                _, stderr = proc.communicate()
                if proc.returncode != 0:
                    raise HybridSourceError("FFmpeg extraction failed: " + stderr.decode("utf-8", errors="replace")[-450:])
            with self._lock:
                if job["status"] == "canceled":
                    return
            frames = sorted(staging.glob("frame_*.png"))
            if not frames:
                raise HybridSourceError("No frames were extracted.")
            if len(frames) > MAX_EXTRACT_FRAMES:
                raise HybridSourceError("Extracted frames exceed the safety limit.")
            manifest = {"source": filename, "start": start, "end": end, "fps": fps,
                        "frames": len(frames), "filenames": [p.name for p in frames]}
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            previous = root / (".previous-" + job_id)
            if destination.exists():
                destination.rename(previous)
            try:
                staging.rename(destination)
            except Exception:
                if previous.exists():
                    previous.rename(destination)
                raise
            shutil.rmtree(previous, ignore_errors=True)
            with self._lock:
                job["status"] = "completed"
                job["frames"] = len(frames)
        except Exception as exc:
            with self._lock:
                if job["status"] != "canceled":
                    job["status"] = "failed"
                    job["error"] = str(exc)[:600]
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
            shutil.rmtree(staging, ignore_errors=True)

    def manifest(self, project_id: str) -> dict[str, Any]:
        root = animation_project_directory(project_id) / "assets" / "hybrid" / "frames"
        path = root / "manifest.json"
        if not path.is_file():
            raise HybridSourceError("No extracted frame sequence for this project.")
        return json.loads(path.read_text(encoding="utf-8"))


hybrid_extraction_manager = HybridExtractionManager()
