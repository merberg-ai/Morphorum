"""Advisory, geometry-free estimates for risky cumulative 3D schedules.

No pixel coverage is predicted. Real coverage requires an image, depth map,
projected frame and selected camera settings. This module uses no GPU.
"""
from __future__ import annotations

import math
from typing import Any

from .animation_resolution import project_schedule_series
from .schedules import ScheduleError

CAMERA_AXES = {
    "translation_x": ("scene units", 0.10, 1.0),
    "translation_y": ("scene units", 0.10, 1.0),
    "translation_z": ("scene units", 0.10, 1.25),
    "rotation_x": ("degrees", 2.0, 30.0),
    "rotation_y": ("degrees", 2.0, 30.0),
    "rotation_z": ("degrees", 2.0, 30.0),
}


def camera_motion_advisories(project: dict[str, Any]) -> dict[str, Any]:
    animation = project.get("animation") or {}
    total = int(animation.get("max_frames") or 0)
    if str(animation.get("mode") or "2d").lower() != "3d" or total < 2:
        return {"sampled_frames": 0, "total_frames": total,
                "issues": [], "basis": "not-applicable"}
    count = min(total, 256)
    step_risk: dict[str, Any] | None = None
    drift_risk: dict[str, Any] | None = None
    moving = False
    sampled = 0
    for axis, (unit, step_limit, drift_limit) in CAMERA_AXES.items():
        field = "camera_3d." + axis
        try:
            values = project_schedule_series(
                project, field, sample_count=count,
            )["samples"]
        except (ScheduleError, TypeError, ValueError, OverflowError):
            continue  # The canonical schedule validator handles invalid inputs.
        sampled = max(sampled, len(values))
        cumulative = 0.0
        previous = 0
        for item in values:
            frame = int(item["frame"])
            value = float(item["value"])
            if frame == 0:
                continue  # Frame 0 is the start image and is not warped.
            if not math.isfinite(value):
                continue
            steps = max(0, frame - previous)
            previous = frame
            cumulative += steps * value
            moving |= abs(value) > 1e-9
            sr = abs(value) / step_limit
            dr = abs(cumulative) / drift_limit
            if sr >= 1.0 and (step_risk is None or sr > step_risk["ratio"]):
                step_risk = dict(axis=axis, field=field, frame=frame,
                                 value=value, unit=unit, ratio=sr)
            if dr >= 1.0 and (drift_risk is None or dr > drift_risk["ratio"]):
                drift_risk = dict(axis=axis, field=field, frame=frame,
                                  value=cumulative, unit=unit, ratio=dr)
    issues: list[dict[str, str]] = []
    if step_risk is not None:
        item = step_risk
        issues.append({
            "severity": "warning", "field": item["field"], "action": "editor",
            "message": (
                f"Frame {item['frame']}: 3D {item['axis']} moves "
                f"{item['value']:+.3g} {item['unit']} per frame. Large per-frame "
                "movement can project the scene outside view. Use gentler "
                "keyframes and inspect Camera Preview."
            ),
        })
    if drift_risk is not None:
        item = drift_risk
        issues.append({
            "severity": "warning", "field": item["field"], "action": "editor",
            "message": (
                f"At approximately frame {item['frame']}, 3D {item['axis']} "
                f"accumulates to {item['value']:+.3g} {item['unit']}. "
                "Each frame moves the camera again; this is not an absolute "
                "destination. Lower sustained motion or add a return keyframe. "
                "This estimate does not predict pixel coverage."
            ),
        })
    if moving:
        try:
            fov = project_schedule_series(
                project, "camera_3d.fov", sample_count=count,
            )["samples"]
            sampled = max(sampled, len(fov))
            narrow = next((point for point in fov
                           if math.isfinite(float(point["value"]))
                           and float(point["value"]) < 20), None)
            if narrow is not None:
                issues.append({
                    "severity": "warning", "field": "camera_3d.fov",
                    "action": "editor",
                    "message": (
                        f"Frame {int(narrow['frame'])}: FOV is "
                        f"{float(narrow['value']):g}°. A narrow view and "
                        "moving camera may lose the scene. Check the actual "
                        "depth projection in Camera Preview."
                    ),
                })
        except (ScheduleError, ValueError, TypeError, OverflowError):
            pass
    return {
        "sampled_frames": sampled, "total_frames": total, "issues": issues,
        "basis": "sampled schedule heuristics, not depth projection",
    }
