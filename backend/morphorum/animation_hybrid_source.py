"""B6.2 opt-in video source probing, without allowing arbitrary host paths.

This module only probes a managed uploaded asset. It does not alter B5
animation generation, extract frames, or enable hybrid render paths.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from .animation_projects import animation_project_directory
from .animation_video import ffmpeg_executable


class HybridSourceError(ValueError):
    pass


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_PROBE_SECONDS = 15


def managed_video_path(project_id: str, filename: str) -> Path:
    if not isinstance(filename, str) or filename != Path(filename).name:
        raise HybridSourceError("Video filename must not contain path components.")
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise HybridSourceError("Unsupported video container; use MP4, MOV, MKV or WebM.")
    # Fixed managed path; never open the filename supplied by imported Deforum settings.
    return animation_project_directory(project_id) / "assets" / "hybrid" / ("source" + suffix)


def _finite_positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _frame_rate(value: Any) -> float | None:
    if isinstance(value, str) and "/" in value:
        left, right = value.split("/", 1)
        numerator, denominator = _finite_positive(left), _finite_positive(right)
        if numerator is None or denominator is None:
            return None
        return numerator / denominator
    return _finite_positive(value)


def parse_ffprobe_json(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise HybridSourceError("FFprobe did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise HybridSourceError("FFprobe returned an invalid result.")
    streams = data.get("streams", [])
    if not isinstance(streams, list):
        raise HybridSourceError("FFprobe streams are invalid.")
    stream = next(
        (item for item in streams
         if isinstance(item, dict) and item.get("codec_type") == "video"
         and item.get("disposition", {}).get("attached_pic", 0) != 1),
        None,
    )
    if stream is None:
        raise HybridSourceError("No usable video stream was found.")
    try:
        width, height = int(stream["width"]), int(stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HybridSourceError("Video dimensions are missing.") from exc
    if not (16 <= width <= 16384 and 16 <= height <= 16384):
        raise HybridSourceError("Video dimensions are outside supported probe bounds.")
    duration = _finite_positive(stream.get("duration")) or _finite_positive(
        (data.get("format") or {}).get("duration")
    )
    fps = _frame_rate(stream.get("avg_frame_rate")) or _frame_rate(
        stream.get("r_frame_rate")
    )
    if duration is None or fps is None or fps > 1000:
        raise HybridSourceError("Video duration or frame rate is missing/invalid.")
    return {
        "width": width, "height": height,
        "duration_seconds": round(duration, 4),
        "fps": round(fps, 5),
        "estimated_frames": max(1, int(math.ceil(duration * fps))),
        "codec": str(stream.get("codec_name") or "unknown")[:80],
        "has_audio": any(
            isinstance(item, dict) and item.get("codec_type") == "audio"
            for item in streams
        ),
    }


def probe_managed_video(project_id: str, filename: str) -> dict[str, Any]:
    path = managed_video_path(project_id, filename)
    if not path.is_file():
        raise HybridSourceError("Managed source video not found.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise HybridSourceError("Source video is empty or exceeds the 512 MiB limit.")
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise HybridSourceError("FFmpeg/FFprobe is not installed.")
    executable = Path(ffmpeg).with_name(
        "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
    )
    if not executable.is_file():
        raise HybridSourceError("FFprobe executable was not found next to FFmpeg.")
    try:
        completed = subprocess.run(
            [str(executable), "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration,disposition:"
             "format=duration", "-of", "json", str(path)],
            check=False, capture_output=True, text=True, timeout=MAX_PROBE_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HybridSourceError("FFprobe failed to inspect the video.") from exc
    if completed.returncode:
        raise HybridSourceError("FFprobe rejected the source video.")
    result = parse_ffprobe_json(completed.stdout)
    result.update({"size_bytes": size, "source": "managed-hybrid-video"})
    return result
