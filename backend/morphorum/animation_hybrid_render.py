"""B6.3.1 deterministic, opt-in hybrid-video frames for diffusion anchors.

No source-video compositing or mask mixing here. The selected extracted PNGs
are frozen into the render directory before the job is queued, so resume never
depends on files that the Source Lab may later replace.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .schedules import ScheduleError, resolve_numeric_schedule, validate_numeric_schedule
from .animation_projects import animation_project_directory

_FILENAME = re.compile(r"frame_[0-9]{6}\.png\Z")
MAX_SOURCE_FRAMES = 1200
MAX_SNAPSHOT_BYTES = 2 * 1024**3


class HybridRenderError(ValueError):
    pass


def normalize_hybrid_settings(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    offset = data.get("offset_frames", 0)
    try:
        offset = int(offset)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HybridRenderError("Hybrid source offset must be a whole number of extracted frames.") from exc
    if not 0 <= offset <= MAX_SOURCE_FRAMES:
        raise HybridRenderError("Hybrid source offset must be between 0 and 1200.")
    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise HybridRenderError("Hybrid source enabled setting must be a boolean.")
    composite_enabled = data.get("composite_enabled", False)
    if not isinstance(composite_enabled, bool):
        raise HybridRenderError("Hybrid compositing enabled setting must be a boolean.")
    opacity_schedule = str(data.get("composite_opacity", "0:(0.35)") or "").strip()
    if len(opacity_schedule) > 1024:
        raise HybridRenderError("Hybrid opacity schedule exceeds 1024 characters.")
    if composite_enabled and not enabled:
        raise HybridRenderError("Enable hybrid video source input before enabling compositing.")
    return {
        "enabled": enabled, "offset_frames": offset, "end_policy": "hold-last",
        "composite_enabled": composite_enabled,
        "composite_opacity": opacity_schedule,
    }


def source_index(frame: int, render_fps: float, source_fps: float, count: int, offset: int = 0) -> int:
    """Map zero-based render frame to one-based extracted source frame by time."""
    if not 0 <= frame or count < 1 or not 0 < render_fps <= 240 or not 0 < source_fps <= 120:
        raise HybridRenderError("Invalid hybrid frame mapping inputs.")
    return min(count, offset + int(math.floor(frame * source_fps / render_fps + 0.5)) + 1)


def freeze_hybrid_source(project: dict[str, Any], render_dir: Path) -> dict[str, Any] | None:
    settings = normalize_hybrid_settings(project.get("hybrid"))
    if not settings["enabled"]:
        return None
    project_id = str(project["id"])
    root = animation_project_directory(project_id) / "assets" / "hybrid" / "frames"
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HybridRenderError("Hybrid render requires extracted frames. Open Media and extract the video first.") from exc
    if not isinstance(manifest, dict):
        raise HybridRenderError("Extracted source manifest is not valid.")
    filenames = manifest.get("filenames")
    try:
        count = int(manifest.get("frames", 0))
        source_fps = float(manifest.get("fps", 0))
        render_fps = float(project["animation"]["fps"])
        total = int(project["animation"]["max_frames"])
    except (TypeError, ValueError, OverflowError, KeyError) as exc:
        raise HybridRenderError("Hybrid source or animation frame metadata is invalid.") from exc
    if not (
        isinstance(filenames, list) and len(filenames) == count
        and 1 <= count <= MAX_SOURCE_FRAMES and 0 < source_fps <= 120
        and math.isfinite(source_fps) and 0 < render_fps <= 240
        and math.isfinite(render_fps) and 1 <= total <= 10_000
    ):
        raise HybridRenderError("Extracted frame manifest has invalid count or frame rates.")
    if any(not isinstance(name, str) or not _FILENAME.fullmatch(name) for name in filenames):
        raise HybridRenderError("Extracted frame manifest contains an unsafe frame filename.")
    if len(set(filenames)) != count:
        raise HybridRenderError("Extracted frame manifest contains duplicate filenames.")
    if settings["offset_frames"] >= count:
        raise HybridRenderError("Hybrid source offset exceeds the extracted frame sequence.")
    if "source_mtime_ns" in manifest or "source_size_bytes" in manifest:
        # Prevent stale frames following a new video upload with the same name.
        from .animation_hybrid_source import managed_video_path
        filename = manifest.get("source")
        try:
            video = managed_video_path(project_id, filename)
            stat = video.stat()
            if (stat.st_size != int(manifest["source_size_bytes"])
                    or stat.st_mtime_ns != int(manifest["source_mtime_ns"])):
                raise HybridRenderError(
                    "The uploaded source video changed after extraction. Extract frames again."
                )
        except HybridRenderError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise HybridRenderError(
                "The extracted video revision cannot be verified. Extract frames again."
            ) from exc

    indices = [
        source_index(frame, render_fps, source_fps, count, settings["offset_frames"])
        for frame in range(total)
    ]
    selected = {filenames[index - 1] for index in indices}
    sources: list[Path] = []
    total_bytes = 0
    for name in sorted(selected):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise HybridRenderError("An extracted hybrid frame is missing or unsafe: " + name)
        total_bytes += path.stat().st_size
        if total_bytes > MAX_SNAPSHOT_BYTES:
            raise HybridRenderError("Hybrid frame snapshot exceeds 2 GiB. Extract a shorter or lower-resolution clip.")
        sources.append(path)

    final = render_dir / "hybrid-source"
    if final.exists():
        raise HybridRenderError("A hybrid snapshot already exists for this render.")
    temp = render_dir / (".hybrid-source-" + uuid.uuid4().hex)
    temp.mkdir(parents=True, exist_ok=False)
    frozen = {
        "enabled": True,
        "mode": "anchor-init",
        "source": str(manifest.get("source") or "extracted video")[:160],
        "source_fps": source_fps,
        "render_fps": render_fps,
        "offset_frames": settings["offset_frames"],
        "end_policy": "hold-last",
        "source_frames": count,
        "frame_indices": indices,
        "source_frame_names": filenames,
    }
    try:
        for path in sources:
            shutil.copy2(path, temp / path.name)
        (temp / "manifest.json").write_text(
            json.dumps(frozen, indent=2) + "\n", encoding="utf-8"
        )
        temp.rename(final)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return frozen


def frozen_hybrid_frame(
    snapshot: dict[str, Any] | None,
    render_dir: Path,
    frame: int,
) -> tuple[Path, dict[str, Any]] | None:
    if not snapshot or not snapshot.get("enabled"):
        return None
    try:
        index = snapshot["frame_indices"][frame]
        filename = snapshot["source_frame_names"][index - 1]
    except (KeyError, IndexError, TypeError) as exc:
        raise HybridRenderError("Frozen hybrid source mapping is incomplete; cannot resume safely.") from exc
    if not isinstance(filename, str) or not _FILENAME.fullmatch(filename):
        raise HybridRenderError("Frozen hybrid source filename is unsafe.")
    path = render_dir / "hybrid-source" / filename
    if not path.is_file() or path.is_symlink():
        raise HybridRenderError("Frozen hybrid source frame is missing: " + filename)
    return path, {
        "source_frame": index,
        "source_filename": filename,
        "source_fps": snapshot["source_fps"],
        "offset_frames": snapshot["offset_frames"],
        "policy": snapshot["end_policy"],
        "mode": snapshot["mode"],
    }


def composite_opacity_for_frame(
    project: dict[str, Any],
    frame: int,
) -> float:
    """Resolve frame opacity from Deforum-style numeric expression schedules."""
    data = project.get("hybrid") or {}
    if not data.get("composite_enabled", False):
        return 0.0
    settings = project.get("animation") or {}
    total = int(settings.get("max_frames", 1))
    fps = float(settings.get("fps", 24))
    seed = max(0, int((project.get("generation") or {}).get("seed", 0)))
    schedule = str(data.get("composite_opacity") or "0:(0.35)")
    try:
        opacity = float(resolve_numeric_schedule(
            schedule, frame=frame, max_frames=total, seed=seed,
            fps=fps, interpolation="linear",
        ))
    except (ScheduleError, TypeError, ValueError, OverflowError) as exc:
        raise HybridRenderError(f"Invalid hybrid opacity schedule at frame {frame}: {exc}") from exc
    if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
        raise HybridRenderError(
            f"Hybrid video opacity at frame {frame} is {opacity:g}; allowed range is 0 to 1."
        )
    return opacity


def validate_hybrid_composite(project: dict[str, Any]) -> None:
    """Reject invalid hybrid schedules before a potentially expensive GPU run."""
    config = normalize_hybrid_settings(project.get("hybrid"))
    if not config["composite_enabled"]:
        return
    animation = project.get("animation") or {}
    total = int(animation.get("max_frames", 1))
    fps = float(animation.get("fps", 24))
    seed = max(0, int((project.get("generation") or {}).get("seed", 0)))
    try:
        result = validate_numeric_schedule(
            config["composite_opacity"], max_frames=total, fps=fps,
            seed=seed, interpolation="linear",
        )
    except (ScheduleError, TypeError, ValueError) as exc:
        raise HybridRenderError(f"Invalid hybrid opacity schedule: {exc}") from exc
    if not result.get("valid"):
        issues = result.get("issues", [])
        message = str(issues[0].get("message", "Invalid expression")) if issues else "Invalid expression"
        raise HybridRenderError("Invalid hybrid opacity schedule: " + message)
    for frame in range(total):
        composite_opacity_for_frame(project, frame)


def blend_hybrid_video(
    generated: Image.Image,
    source: Image.Image,
    opacity: float,
) -> Image.Image:
    """Composite source video over the completed diffusion/temporal frame."""
    if not 0.0 <= opacity <= 1.0 or not math.isfinite(opacity):
        raise HybridRenderError("Hybrid compositing opacity must be between 0 and 1.")
    base = generated.convert("RGB")
    if opacity == 0.0:
        return base
    overlay = ImageOps.fit(
        ImageOps.exif_transpose(source).convert("RGB"),
        base.size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5),
    )
    if opacity == 1.0:
        return overlay
    return Image.blend(base, overlay, opacity)
