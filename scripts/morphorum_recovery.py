"""DB2.4 standalone durable native-client render session.

A saved session contains a frozen *project request* and a stable Idempotency-Key,
but no authentication token. It can safely retry after an ambiguous HTTP timeout.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import quote

from morphorum_client import ClientError, MorphorumClient

_TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class RecoveryError(RuntimeError):
    pass


class SessionFile:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> dict:
        if not self.path.is_file() or self.path.is_symlink():
            raise RecoveryError("Session file is missing or unsafe.")
        if os.name != "nt" and stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise RecoveryError("Session file has unsafe permissions; use chmod 600.")
        if self.path.stat().st_size > 3 * 1024 * 1024:
            raise RecoveryError("Session file is unreasonably large.")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RecoveryError("Session file cannot be read.") from exc
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or not isinstance(data.get("backend_instance_id"), str)
                or not isinstance(data.get("idempotency_key"), str)
                or not isinstance(data.get("payload"), dict)
                or "project" not in data["payload"]):
            raise RecoveryError("Session file is invalid.")
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RecoveryError("Refusing to overwrite symlink session.")
        name = "." + self.path.name + "." + secrets.token_hex(8) + ".tmp"
        temp = self.path.with_name(name)
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(data, output, separators=(",", ":"), ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)


def prepare(client: MorphorumClient, project_id: str, output: SessionFile) -> dict:
    """Freeze exact payload and job key to disk BEFORE sending the first POST."""
    if output.path.exists():
        raise RecoveryError("Session already exists; use attach instead.")
    handshake = client.handshake()
    project = client.request(
        "GET", f"/api/animation/projects/{quote(project_id, safe='')}"
    )["project"]
    payload = {"project": project}
    session = {
        "schema_version": 1,
        "backend_url": client.base_url,
        "backend_instance_id": handshake["instance_id"],
        "last_boot_id": handshake["boot_id"],
        "project_id": project_id,
        "kind": "animation",
        "payload": payload,
        "payload_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "idempotency_key": secrets.token_hex(20),
        "render_id": None,
        "last_frame": -1,
    }
    output.save(session)
    return session


def attach(client: MorphorumClient, session_file: SessionFile) -> tuple[dict, dict, bool]:
    """Reconcile a persistent session, never submitting a second render."""
    session = session_file.load()
    info = client.handshake()
    if client.base_url != session["backend_url"]:
        raise RecoveryError("Saved session targets a different backend URL.")
    if info["instance_id"] != session["backend_instance_id"]:
        raise RecoveryError("Backend instance changed; refusing automatic reattachment.")
    restarted = session["last_boot_id"] != info["boot_id"]
    session["last_boot_id"] = info["boot_id"]

    if session.get("render_id"):
        result = client.request(
            "GET", f"/api/animation/renders/{quote(session['render_id'], safe='')}"
        )
    else:
        # The response to the original POST may have been lost. Replay the
        # same exact body and key rather than creating a second GPU job.
        result = client.request(
            "POST", "/api/animation/renders", payload=session["payload"],
            headers={"Idempotency-Key": session["idempotency_key"]},
        )
        session["render_id"] = result["id"]
    session_file.save(session)
    return session, result, restarted


def sync_completed_frames(
    client: MorphorumClient, session_file: SessionFile,
    job: dict, directory: Path, *, max_downloads: int = 50,
) -> int:
    """Recover all known completed frames, not only the most recent thumbnail."""
    session = session_file.load()
    directory.mkdir(parents=True, exist_ok=True)
    available = sorted({
        int(item["frame"]) for item in job.get("results", [])
        if isinstance(item, dict) and str(item.get("frame", "")).isdigit()
    })
    if not available and isinstance(job.get("latest_completed_frame"), int):
        # A compact status can carry only the newest frame. Fetch it, but do
        # not claim earlier frames have been recovered.
        available = [job["latest_completed_frame"]]
    count = 0
    for frame in available:
        target = directory / f"frame_{frame:06d}.png"
        if target.is_file() and target.stat().st_size > 8:
            with target.open("rb") as check:
                if check.read(8) == b"\x89PNG\r\n\x1a\n":
                    continue
        path = (f"/api/animation/renders/{quote(session['project_id'], safe='')}/"
                f"{quote(session['render_id'], safe='')}/frames/{frame}")
        client.download(path, target, file_type="png")
        count += 1
        if count >= max_downloads:
            break
    if available:
        session["last_frame"] = max(session.get("last_frame", -1), max(available))
        session_file.save(session)
    return count


def watch_session(client: MorphorumClient, session_file: SessionFile,
                  *, frames_dir: Path | None = None, interval: float = 2.0,
                  max_seconds: float = 3600) -> dict:
    import time

    session, job, restarted = attach(client, session_file)
    print(f"[PASS] Session reattached: {session['render_id']}", flush=True)
    if restarted:
        print("[INFO] Backend restarted; console/event cursors must reset.", flush=True)
    end = time.monotonic() + max_seconds
    previous = None
    while time.monotonic() < end:
        state = (job.get("status"), job.get("current_frame"), job.get("current_step"),
                 round(float(job.get("progress") or 0), 3),
                 job.get("latest_completed_frame"))
        if state != previous:
            print(f"[PROGRESS] {state[0]} {float(job.get('progress') or 0) * 100:.1f}% "
                  f"frame={state[1]} step={state[2]}", flush=True)
            previous = state
        if frames_dir:
            obtained = sync_completed_frames(client, session_file, job, frames_dir)
            if obtained:
                print(f"[PASS] Retrieved {obtained} additional completed frame(s).", flush=True)
        if job.get("status") in _TERMINAL:
            print(f"[PASS] Reached terminal state: {job['status']}", flush=True)
            if job.get("status") == "completed" and job.get("preview_url"):
                target = session_file.path.with_suffix(".gif")
                client.download(job["preview_url"], target, file_type="gif")
                print("[PASS] Retrieved completed GIF:", target, flush=True)
            return job
        time.sleep(interval)
        try:
            job = client.request(
                "GET", f"/api/animation/renders/{quote(session['render_id'], safe='')}"
            )
        except ClientError:
            # The backend keeps rendering. Reconnect the same session by GET,
            # never inventing a new request key or cancelling GPU work.
            print("[WARN] Connection interrupted; reconnecting to existing render.", flush=True)
            recovered = False
            for attempt in range(5):
                time.sleep(min(8.0, 0.5 * 2 ** attempt))
                try:
                    session, job, boot_changed = attach(client, session_file)
                    if boot_changed:
                        print("[INFO] Backend process changed; refetched job state.", flush=True)
                    print("[PASS] Connection restored; same render ID.", flush=True)
                    recovered = True
                    break
                except ClientError:
                    continue
            if not recovered:
                raise RecoveryError(
                    "Network remains offline; saved session is safe. Run attach later."
                )
    raise RecoveryError("Watch timed out; job may still be running. Run attach again.")
