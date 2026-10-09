"""B5.5 low-overhead, restart-safe animation performance accounting.

No GPU synchronization or tensor retention; writes one small JSONL record per
completed frame, including recorded adapter counts and memory snapshots.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _finite_seconds(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return max(0.0, number) if math.isfinite(number) else 0.0


def _memory_fields(sample: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(sample, dict):
        return None
    result: dict[str, float] = {}
    for key in ("free_gib", "total_gib", "allocated_gib", "reserved_gib",
                "peak_allocated_gib", "peak_reserved_gib"):
        try:
            value = float(sample[key])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value):
            result[key] = round(value, 4)
    return result or None


@dataclass
class AnimationPerformance:
    frames: int = 0
    anchors: int = 0
    cumulative_seconds: float = 0.0
    cumulative_diffusion_seconds: float = 0.0
    cumulative_prepare_seconds: float = 0.0
    cumulative_conditioning_seconds: float = 0.0
    maximum_frame_seconds: float = 0.0
    maximum_allocated_gib: float = 0.0
    maximum_reserved_gib: float = 0.0
    maximum_resident_loras: int = 0
    first_memory: dict[str, float] | None = None
    last_memory: dict[str, float] | None = None
    latest_frame: int | None = None
    latest_diffusion_seconds: float = 0.0
    last_device: str | None = None
    last_optimization: str | None = None
    slow_anchor_frames: list[int] = field(default_factory=list)

    def observe(self, record: dict[str, Any]) -> None:
        self.frames += 1
        self.latest_frame = int(record["frame"])
        self.anchors += int(bool(record.get("diffused")))
        times = record.get("timings") or {}
        total = _finite_seconds(times.get("total"))
        diffusion = _finite_seconds(times.get("diffusion"))
        self.cumulative_seconds += total
        self.cumulative_diffusion_seconds += diffusion
        self.cumulative_prepare_seconds += _finite_seconds(times.get("prepare"))
        self.cumulative_conditioning_seconds += _finite_seconds(times.get("conditioning"))
        self.maximum_frame_seconds = max(self.maximum_frame_seconds, total)
        self.latest_diffusion_seconds = diffusion
        self.last_device = str(record.get("pipeline_device") or "") or self.last_device
        self.last_optimization = str(record.get("optimization") or "") or self.last_optimization
        self.maximum_resident_loras = max(
            self.maximum_resident_loras,
            int(record.get("resident_loras") or 0),
        )
        memory = _memory_fields(record.get("cuda_after"))
        if memory:
            if self.first_memory is None:
                self.first_memory = _memory_fields(record.get("cuda_before")) or memory
            self.last_memory = memory
            self.maximum_allocated_gib = max(
                self.maximum_allocated_gib, memory.get("allocated_gib", 0.0),
            )
            self.maximum_reserved_gib = max(
                self.maximum_reserved_gib, memory.get("reserved_gib", 0.0),
            )

        # Local, observational warning only; not a hard-coded baseline speed.
        # Keep bounded data and report it instead of silently changing devices.
        if record.get("diffused") and diffusion >= 30.0:
            self.slow_anchor_frames.append(self.latest_frame)
            self.slow_anchor_frames = self.slow_anchor_frames[-24:]

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "frames_observed": self.frames,
            "diffusion_anchors": self.anchors,
            "average_frame_seconds": round(
                self.cumulative_seconds / self.frames, 3
            ) if self.frames else None,
            "average_anchor_diffusion_seconds": round(
                self.cumulative_diffusion_seconds / self.anchors, 3
            ) if self.anchors else None,
            "total_frame_seconds": round(self.cumulative_seconds, 3),
            "total_diffusion_seconds": round(self.cumulative_diffusion_seconds, 3),
            "total_prepare_seconds": round(self.cumulative_prepare_seconds, 3),
            "total_conditioning_seconds": round(self.cumulative_conditioning_seconds, 3),
            "maximum_frame_seconds": round(self.maximum_frame_seconds, 3),
            "maximum_allocated_gib": round(self.maximum_allocated_gib, 3),
            "maximum_reserved_gib": round(self.maximum_reserved_gib, 3),
            "maximum_resident_loras": self.maximum_resident_loras,
            "first_memory": self.first_memory,
            "last_memory": self.last_memory,
            "latest_frame": self.latest_frame,
            "latest_diffusion_seconds": round(self.latest_diffusion_seconds, 3),
            "pipeline_device": self.last_device,
            "optimization": self.last_optimization,
            "slow_anchor_frames": list(self.slow_anchor_frames),
        }


def performance_record(
    *,
    frame: int,
    diffused: bool,
    timings: dict[str, Any],
    cuda_before: dict[str, Any] | None,
    cuda_after: dict[str, Any] | None,
    model_status: dict[str, Any] | None,
    conditioning_cache_entries: int,
) -> dict[str, Any]:
    model_status = model_status if isinstance(model_status, dict) else {}
    return {
        "schema_version": 1,
        "frame": int(frame),
        "diffused": bool(diffused),
        "timings": {
            key: round(_finite_seconds(timings.get(key)), 4)
            for key in (
                "total", "prepare", "conditioning", "diffusion",
                "warp", "depth", "temporal", "save", "manifest", "memory",
            )
        },
        "cuda_before": _memory_fields(cuda_before),
        "cuda_after": _memory_fields(cuda_after),
        "pipeline_device": model_status.get("device"),
        "optimization": model_status.get("optimization"),
        "pipeline_task": model_status.get("task"),
        "resident_loras": len(model_status.get("loras") or []),
        "active_loras": [
            {"adapter_name": item.get("adapter_name"),
             "weight": float(item.get("weight", 0.0))}
            for item in model_status.get("active_loras") or []
        ],
        "conditioning_cache_entries": int(conditioning_cache_entries),
    }


def append_performance_record(path: Path, record: dict[str, Any]) -> None:
    """Append only a completed frame; no model writes or expensive fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_performance_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    by_frame: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and isinstance(value.get("frame"), int):
                by_frame[value["frame"]] = value
        except (ValueError, TypeError):
            # A killed process may leave a truncated final JSONL line.
            continue
    return [by_frame[index] for index in sorted(by_frame)]


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    tracker = AnimationPerformance()
    for record in records:
        tracker.observe(record)
    return tracker.public()
