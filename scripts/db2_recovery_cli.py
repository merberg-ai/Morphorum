#!/usr/bin/env python3
"""DB2.4 remote render start/reattach with short phone-friendly output.

Python standard library only; requires morphorum_client.py and
morphorum_recovery.py in the same folder. Never logs bearer credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

from morphorum_client import ClientError, MorphorumClient
from morphorum_recovery import (
    RecoveryError, SessionFile, attach, prepare, watch_session,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Morphorum DB2.4 recovery acceptance")
    parser.add_argument("--url", default="http://192.168.1.24:7866")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--session", default=str(Path.home() / "tmp/db2-render-session.json"))
    parser.add_argument("--frames-dir", help="Optional local directory to recover completed PNGs.")
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start", help="Create durable session and submit one render.")
    start.add_argument("project_id", help="Existing, camera-verified project ID.")
    start.add_argument("--watch", action="store_true")
    sub.add_parser("attach", help="Reattach an existing session, without new work.")
    probe = sub.add_parser("probe", help="Read-only recovery preflight for an existing job.")
    probe.add_argument("render_id")
    args = parser.parse_args()

    try:
        secret = Path(args.token_file).expanduser().read_text(encoding="ascii").strip()
        client = MorphorumClient(args.url, secret, timeout=20)
        session_file = SessionFile(args.session)
        frames = Path(args.frames_dir).expanduser() if args.frames_dir else None
        if args.action == "start":
            prepare(client, args.project_id, session_file)
            print("[PASS] Durable submission session prepared before POST", flush=True)
            try:
                session, job, _ = attach(client, session_file)
            except ClientError:
                print("[WARN] Request result uncertain. Run 'attach' with the same session.", flush=True)
                raise
            print("[PASS] Render ID:", job["id"], flush=True)
            print("[PASS] Idempotency key saved locally (not printed).", flush=True)
            print("[INFO] Re-running attach will NOT create another render.", flush=True)
            if args.watch:
                result = watch_session(client, session_file, frames_dir=frames)
                return 0 if result.get("status") == "completed" else 1
            print("RESULT: PASS", flush=True)
            return 0
        if args.action == "attach":
            result = watch_session(client, session_file, frames_dir=frames)
            return 0 if result.get("status") == "completed" else 1

        info = client.handshake()
        record = client.request(
            "GET", f"/api/animation/renders/{quote(args.render_id, safe='')}"
        )
        print("[PASS] Authenticated API handshake", flush=True)
        print("[PASS] Existing render found:", record.get("id"), flush=True)
        print("[PASS] Render status:", record.get("status"), flush=True)
        url = f"/api/client/jobs/animation/{quote(args.render_id, safe='')}/events"
        from urllib.request import Request
        request = Request(client.base_url + url, headers={
            "Authorization": "Bearer " + secret,
        })
        # Read only one event. Never block indefinitely on an active render.
        with client._opener.open(request, timeout=15) as response:
            chunk = response.readline(4096)
            if not chunk.startswith(b"id:"):
                raise RecoveryError("Job event stream did not start with an event ID.")
            response.readline(4096)
            payload = response.readline(4096)
            if not payload.startswith(b"data:"):
                raise RecoveryError("Job event stream omitted event data.")
        print("[PASS] Typed job event stream", flush=True)
        print("[PASS] Boot ID:", info["boot_id"][:12] + "...", flush=True)
        print("RESULT: 5/5 PASSED", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\n[INFO] Client monitoring stopped. GPU job was NOT cancelled.", flush=True)
        print("[INFO] Re-run 'attach' with the same session.", flush=True)
        return 130
    except (ClientError, RecoveryError, OSError, ValueError, KeyError) as exc:
        print("[FAIL]", str(exc), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
