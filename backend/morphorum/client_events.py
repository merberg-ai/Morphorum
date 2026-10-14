"""DB2.4 typed SSE job snapshots with polling as the authoritative fallback.

Live events are intentionally ephemeral; the stream has no durable replay log.
Clients MUST GET the job after reconnect to recover status and completed frames.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Callable

from .client_protocol import BOOT_ID

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _event(name: str, data: dict[str, Any], index: int) -> str:
    return (f"id: {BOOT_ID}:{index}\nevent: {name}\n"
            f"data: {json.dumps(data, separators=(',', ':'), ensure_ascii=False)}\n\n")


def _compact(job: dict[str, Any], kind: str) -> dict[str, Any]:
    keys = (
        "id", "project_id", "status", "message", "progress", "eta_seconds",
        "current_frame", "total_frames", "current_step", "current_step_total",
        "load_progress", "load_phase", "load_message",
        "current_prompt_state", "current_frame_state",
        "latest_completed_frame", "latest_frame_url", "preview_url",
        "resumable", "error", "results", "bytes",
    )
    # Do not replay thousands of frame entries in every live event.
    return {"kind": kind, "boot_id": BOOT_ID, **{
        k: v for k in keys if k in job and k != "results"
        for v in [job[k]]
    }}


async def job_event_stream(
    kind: str,
    get_job: Callable[[], dict[str, Any]],
    *,
    previous_boot_id: str | None = None,
    poll_seconds: float = 0.75,
) -> AsyncIterator[str]:
    """Emit current state on attach and changes thereafter; no GPU side effects."""
    sequence = 0
    if previous_boot_id and previous_boot_id != BOOT_ID:
        sequence += 1
        yield _event("stream_reset", {
            "boot_id": BOOT_ID, "reason": "backend_restarted",
            "action": "refetch_job_and_completed_frames",
        }, sequence)
    previous = None
    last_frame: int | None = None
    last_heartbeat = time.monotonic()
    while True:
        job = get_job()
        payload = _compact(job, kind)
        status = str(job.get("status") or "")
        serialized = json.dumps(payload, sort_keys=True, default=str)
        if serialized != previous:
            sequence += 1
            yield _event("job_snapshot" if previous is None else "job_progress",
                         payload, sequence)
            previous = serialized
        frame = job.get("latest_completed_frame")
        if kind == "animation" and isinstance(frame, int) and frame >= 0:
            if last_frame is None or frame > last_frame:
                sequence += 1
                yield _event("frame_ready", {
                    "id": job.get("id"), "project_id": job.get("project_id"),
                    "latest_completed_frame": frame,
                    "latest_frame_url": job.get("latest_frame_url"),
                    "boot_id": BOOT_ID,
                    "hint": "GET job results to recover skipped intermediate frames",
                }, sequence)
                last_frame = frame
        if status in TERMINAL:
            sequence += 1
            yield _event("job_completed" if status == "completed" else "job_ended",
                         payload, sequence)
            break
        if time.monotonic() - last_heartbeat >= 15:
            yield ": heartbeat\n\n"
            last_heartbeat = time.monotonic()
        await asyncio.sleep(max(0.1, poll_seconds))
