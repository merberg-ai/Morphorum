#!/usr/bin/env python3
"""DB2.5 phone-friendly backend integration acceptance (no GPU diffusion).

Commands: preflight, record-boot, verify-boot, lost-response, video.
Uses the verified DB2.4 session for safe, no-new-GPU idempotency retries,
and an optional locally generated one-second audio/video fixture for FFmpeg.
Never prints or writes the bearer token. No network admin actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from morphorum_client import ClientError, MorphorumClient
from morphorum_recovery import RecoveryError, SessionFile


class Failure(RuntimeError):
    pass


class Checks:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.logs = []

    def ok(self, description: str, condition: bool, detail: str = "") -> None:
        status = "PASS" if condition else "FAIL"
        self.logs.append(f"[{status}] {description}" + (": " + detail if detail else ""))
        print(f"[{status}] {description}", flush=True)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            raise Failure(description + (": " + detail if detail else ""))

    def note(self, message: str) -> None:
        self.logs.append("[INFO] " + message)
        print("[INFO] " + message, flush=True)

    def finish(self, action: str) -> int:
        path = Path.home() / "tmp" / ("db25-" + action + ".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.logs) +
                        f"\nRESULT: {self.passed} passed, {self.failed} failed\n",
                        encoding="utf-8")
        print(f"RESULT: {self.passed}/{self.passed + self.failed} PASSED", flush=True)
        print("Details: " + str(path), flush=True)
        return 1 if self.failed else 0


def _atomic_json(path: Path, data: dict) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise Failure("Refusing to overwrite a symlink record.")
    temp = path.with_name("." + path.name + "." + secrets.token_hex(8))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    path = Path(path).expanduser()
    if not path.is_file() or path.is_symlink():
        raise Failure("Expected local acceptance record does not exist.")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _render(client: MorphorumClient, session: dict) -> dict:
    return client.request(
        "GET", f"/api/animation/renders/{quote(session['render_id'], safe='')}"
    )


def _completed_session(client: MorphorumClient, path: Path) -> tuple[dict, dict]:
    session = SessionFile(path).load()
    if not session.get("render_id"):
        raise Failure("Previous DB2.4 render session has no accepted render ID.")
    if client.base_url != session.get("backend_url"):
        raise Failure("Saved session refers to another backend URL.")
    job = _render(client, session)
    if job.get("id") != session["render_id"]:
        raise Failure("Job response does not match the saved render ID.")
    if job.get("status") != "completed":
        raise Failure("DB2.5 safe replay requires a *completed* original render.")
    return session, job


def preflight(client: MorphorumClient, checks: Checks, args) -> None:
    cap = client.handshake()
    checks.ok("Authenticated backend handshake", cap.get("api_contract_version") == 1)
    checks.ok("DB2 discovery features available", all(
        cap.get("features", {}).get(f) is True for f in (
            "idempotent_submissions", "job_events_sse", "project_asset_listing",
            "soundtrack_attachment_download", "conditional_project_saves"
        )))
    session, job = _completed_session(client, args.session)
    checks.ok("Existing DB2.4 render is completed", job.get("status") == "completed")
    checks.ok("Backend installation identity unchanged",
              cap.get("instance_id") == session.get("backend_instance_id"))
    checks.ok("Saved rendered frames accessible",
              job.get("latest_completed_frame") is not None
              and isinstance(job.get("results"), list))
    video = client.request("GET", "/api/animation/video/availability")
    checks.ok("Video export API reachable", "available" in video and "formats" in video)
    checks.note("Host FFmpeg: " + ("available" if video["available"] else "unavailable"))
    checks.note("Current boot ID prefix: " + cap["boot_id"][:12])


def record_boot(client: MorphorumClient, checks: Checks, args) -> None:
    cap = client.handshake()
    session, job = _completed_session(client, args.session)
    checks.ok("Existing completed render accessible", job.get("status") == "completed")
    checks.ok("Correct installation before restart",
              cap["instance_id"] == session["backend_instance_id"])
    _atomic_json(args.boot_record, {
        "instance_id": cap["instance_id"], "boot_id": cap["boot_id"],
        "render_id": session["render_id"], "backend_url": client.base_url,
    })
    checks.note("Boot ID recorded. Restart ONLY the backend application on the Omen.")


def verify_boot(client: MorphorumClient, checks: Checks, args) -> None:
    prior = _read_json(args.boot_record)
    cap = client.handshake()
    checks.ok("Backend URL unchanged", client.base_url == prior["backend_url"])
    checks.ok("Installation ID preserved", cap["instance_id"] == prior["instance_id"])
    checks.ok("Backend process boot ID changed", cap["boot_id"] != prior["boot_id"])
    session, job = _completed_session(client, args.session)
    checks.ok("Original completed render still retrievable",
              job["id"] == prior["render_id"])
    destination = Path.home() / "tmp/db25-restarted.gif"
    client.download(job["preview_url"], destination, file_type="gif")
    checks.ok("Final GIF download survives restart", destination.stat().st_size > 8)


def lost_response(client: MorphorumClient, checks: Checks, args) -> None:
    """Deliberately discard a response to a *previously completed*, keyed job."""
    cap = client.handshake()
    session, job = _completed_session(client, args.session)
    checks.ok("Original job finished; no GPU submission needed",
              job["status"] == "completed"
              and cap["instance_id"] == session["backend_instance_id"])
    project = quote(session["project_id"], safe="")
    url = f"/api/animation/projects/{project}/renders"
    initial = client.request("GET", url)["renders"]
    existing_ids = {r["id"] for r in initial}

    class SimulatedResponseLoss(RuntimeError):
        pass

    try:
        accepted = client.request(
            "POST", "/api/animation/renders", payload=session["payload"],
            headers={"Idempotency-Key": session["idempotency_key"]}
        )
        if accepted["id"] != session["render_id"]:
            raise Failure("Idempotency returned the wrong render ID.")
        # We intentionally discard the accepted response here.
        raise SimulatedResponseLoss("Simulated client-side dropped HTTP response")
    except SimulatedResponseLoss:
        checks.ok("Lost HTTP response simulated safely", True)

    retried = client.request(
        "POST", "/api/animation/renders", payload=session["payload"],
        headers={"Idempotency-Key": session["idempotency_key"]},
    )
    checks.ok("Exact request replay returns original render ID",
              retried.get("id") == session["render_id"]
              and retried.get("idempotency_replayed") is True)
    current = {r["id"] for r in client.request("GET", url)["renders"]}
    checks.ok("No duplicate GPU job created", existing_ids == current)


def _find_fixture(client: MorphorumClient) -> tuple[str, str]:
    projects = [
        p for p in client.projects()
        if str(p.get("name", "")).startswith("DB25 Audio Fixture ")
    ]
    if len(projects) != 1:
        raise Failure("Expected exactly one disposable DB25 Audio Fixture project.")
    project_id = projects[0]["id"]
    renders = client.request(
        "GET", f"/api/animation/projects/{quote(project_id, safe='')}/renders"
    )["renders"]
    marked = [
        r for r in renders
        if r.get("status") == "completed"
        and str(r.get("id", "")).startswith("anim-db25-fixture-")
    ]
    if len(marked) != 1:
        raise Failure("Expected one completed synthetic audio fixture render.")
    return project_id, marked[0]["id"]


def _probe_file(path: Path, require_audio: bool, checks: Checks) -> None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        if require_audio:
            raise Failure("ffprobe is needed for real audio-track verification; install FFmpeg/ffprobe on Ubuntu Mini.")
        checks.note("ffprobe unavailable: MP4 container recognized; codec streams not checked.")
        return
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=codec_type,codec_name", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise Failure("ffprobe cannot decode downloaded video metadata: " +
                      result.stderr[-250:])
    streams = json.loads(result.stdout).get("streams", [])
    checks.ok("Video stream decodable by ffprobe",
              any(i.get("codec_type") == "video" for i in streams))
    if require_audio:
        checks.ok("Audio stream present in downloaded video",
                  any(i.get("codec_type") == "audio" for i in streams))


def video_export(client: MorphorumClient, checks: Checks, args) -> None:
    cap = client.handshake()
    checks.ok("Authenticated API supports video export",
              cap.get("features", {}).get("video_export") is True)
    project, render_id = _find_fixture(client) if args.fixture else (
        args.project, args.render
    )
    if not project or not render_id:
        raise Failure("Supply --fixture or --project + --render.")
    job = client.request(
        "GET", f"/api/animation/renders/{quote(render_id, safe='')}"
    )
    checks.ok("Completed source render available",
              job.get("status") == "completed" and job.get("project_id") == project)
    submission = {"format": args.format, "quality": "compact"}
    receipt = Path.home() / "tmp" / ("db25-video-" + args.format + ".json")
    if receipt.exists():
        saved = _read_json(receipt)
        if (saved.get("backend_url") != client.base_url
                or saved.get("instance_id") != cap["instance_id"]
                or saved.get("project_id") != project
                or saved.get("render_id") != render_id
                or saved.get("submission") != submission):
            raise Failure("Existing video session is for different work; refuse automatic replacement.")
    else:
        saved = {
            "backend_url": client.base_url, "instance_id": cap["instance_id"],
            "project_id": project, "render_id": render_id,
            "submission": submission, "idempotency_key": secrets.token_hex(20),
            "job_id": None,
        }
        _atomic_json(receipt, saved)
    checks.ok("Durable video-export session available", True)
    video_path = (f"/api/animation/renders/{quote(project, safe='')}/"
                  f"{quote(render_id, safe='')}/video")
    archived = client.request("GET", video_path + "s")["exports"]
    matching = [
        r for r in archived
        if r.get("status") == "completed"
        and r.get("format") == args.format and r.get("quality") == "compact"
    ]
    current = None
    if saved.get("job_id"):
        try:
            current = client.request("GET", f"/api/animation/video/jobs/{saved['job_id']}")
        except ClientError as exc:
            if exc.status != 404:
                raise
    if current is None and matching:
        current = matching[0]
        checks.note("Recovered completed video export from disk record.")
    if current is None:
        current = client.request("POST", video_path, payload=submission,
                                 headers={"Idempotency-Key": saved["idempotency_key"]})
        saved["job_id"] = current["id"]
        _atomic_json(receipt, saved)
    checks.ok("Video export job acknowledged", isinstance(current.get("id"), str))
    if current.get("status") not in {"completed", "failed", "cancelled", "interrupted"}:
        end = time.monotonic() + 240
        prev = None
        while time.monotonic() < end:
            current = client.request("GET", f"/api/animation/video/jobs/{current['id']}")
            state = (current.get("status"), round(float(current.get("progress") or 0), 1))
            if state != prev:
                checks.note("Video export: " + str(state[0]) + " " +
                            str(int(float(current.get("progress") or 0) * 100)) + "%")
                prev = state
            if state[0] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(1)
    checks.ok("FFmpeg encoding completed", current.get("status") == "completed",
              str(current.get("error") or current.get("message") or "")[:180])
    checks.ok("Frozen soundtrack included",
              current.get("audio_included") is True if args.require_audio else True)
    remote_url = current.get("url")
    if not remote_url:
        refreshed = client.request("GET", video_path + "s")["exports"]
        remote_url = next(
            (item.get("url") for item in refreshed if item.get("format") == args.format
             and item.get("quality") == "compact" and item.get("status") == "completed"),
            None,
        )
    if not remote_url:
        raise Failure("Completed video has no download URL.")
    digest = current.get("sha256")
    checks.ok("Export SHA-256 advertised",
              isinstance(digest, str) and len(digest) == 64)
    destination = Path.home() / "tmp" / ("db25-export." + args.format)
    client.download(remote_url, destination, file_type=args.format, expected_sha256=digest)
    checks.ok("Video downloaded with verified SHA-256", destination.stat().st_size > 100)
    _probe_file(destination, args.require_audio, checks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://192.168.1.24:7866")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--session", type=Path,
                        default=Path.home() / "tmp/db2-render-session.json")
    parser.add_argument("--boot-record", type=Path,
                        default=Path.home() / "tmp/db25-boot.json")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("preflight")
    sub.add_parser("record-boot")
    sub.add_parser("verify-boot")
    sub.add_parser("lost-response")
    video = sub.add_parser("video")
    video.add_argument("--fixture", action="store_true",
                       help="Select a synthetic DB25 Audio Fixture; no GPU needed.")
    video.add_argument("--project")
    video.add_argument("--render")
    video.add_argument("--format", choices=("mp4", "webm"), default="mp4")
    video.add_argument("--require-audio", action="store_true")
    args = parser.parse_args()
    checks = Checks()
    try:
        token = Path(args.token_file).expanduser().read_text(encoding="ascii").strip()
        client = MorphorumClient(args.url, token, timeout=20)
        {
            "preflight": preflight, "record-boot": record_boot,
            "verify-boot": verify_boot, "lost-response": lost_response,
            "video": video_export,
        }[args.action](client, checks, args)
    except (Failure, ClientError, RecoveryError, OSError, ValueError, KeyError,
            subprocess.TimeoutExpired) as exc:
        if checks.failed == 0:
            checks.failed += 1
        checks.note("Error: " + type(exc).__name__ + ": " + str(exc))
        print("[FAIL] " + str(exc), file=sys.stderr, flush=True)
    return checks.finish(args.action)


if __name__ == "__main__":
    raise SystemExit(main())
