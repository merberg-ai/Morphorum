"""DB2.4 optional durable idempotency for backend client POST submissions.

A pending record is written before creating any GPU work. If the process dies
after creating a job but before saving its response, retrying gives an
explicit uncertain/pending error rather than starting another expensive job.
Use a single host process for this journal; there is no cross-host locking.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import Request

from .paths import DATA_DIR, ensure_runtime_dirs

JOURNAL_DIR = DATA_DIR / "client-submissions"
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_LOCK = threading.RLock()
_MAX_JOURNAL_BYTES = 128 * 1024


class SubmissionConflict(RuntimeError):
    pass


class SubmissionPending(SubmissionConflict):
    pass


def _canonical_sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _path(scope: str, operation: str, key: str) -> Path:
    identity = hashlib.sha256(
        (scope + "\n" + operation + "\n" + key).encode("utf-8")
    ).hexdigest()
    return JOURNAL_DIR / f"{identity}.json"


def _caller(request: Request) -> str:
    # The bearer token is not recorded; same token/operation/key is same client.
    offered = request.headers.get("authorization", "")
    return ("token-" + hashlib.sha256(offered.encode("utf-8")).hexdigest()
            if offered.startswith("Bearer ") else "standard-local")


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise SubmissionConflict("Submission journal entry is not a regular file.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SubmissionConflict("Submission journal permissions are unsafe.")
    if path.stat().st_size > _MAX_JOURNAL_BYTES:
        raise SubmissionConflict("Submission journal entry exceeds its size bound.")
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SubmissionConflict("Submission journal entry cannot be read.") from exc
    if (not isinstance(entry, dict) or
            entry.get("schema_version") != 1 or
            entry.get("state") not in {"pending", "complete"} or
            not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("payload_sha256", "")))):
        raise SubmissionConflict("Submission journal entry is invalid.")
    return entry


def _write(path: Path, entry: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise SubmissionConflict("Submission journal path must not be a symlink.")
    temp = path.with_name("." + path.stem + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(entry, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def submit_once(
    request: Request,
    *,
    operation: str,
    payload: dict[str, Any],
    submit: Callable[[], dict[str, Any]],
    lookup: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Execute a keyed POST no more than once per caller/key/payload.

    Unkeyed legacy browser requests pass straight through. Known results
    survive a backend process restart. Unknown *pending* records do not.
    """
    key = request.headers.get("idempotency-key")
    if key is None:
        return submit()
    if not _KEY.fullmatch(key):
        raise ValueError("Idempotency-Key must be 8-128 ASCII letters, numbers, . _ : or -.")
    digest = _canonical_sha(payload)
    path = _path(_caller(request), operation, key)

    with _LOCK:
        record = _read(path)
        if record is not None:
            if record["payload_sha256"] != digest:
                raise SubmissionConflict("Idempotency key reused with a different request body.")
            if record["state"] != "complete":
                raise SubmissionPending(
                    "Submission outcome is uncertain. Inspect existing project jobs "
                    "before retrying with a different key."
                )
            initial = record.get("result")
            if not isinstance(initial, dict) or not isinstance(initial.get("id"), str):
                raise SubmissionConflict("Submission journal completed record is invalid.")
            if lookup:
                try:
                    refreshed = lookup(initial["id"])
                    if refreshed is not None:
                        return {**refreshed, "idempotency_replayed": True}
                except Exception:
                    pass
            # A completed journal entry is proof that a job was submitted,
            # NOT proof that its worker survived a server restart. Never
            # report an old "queued" or "generating" state as live.
            return {
                **initial, "status": "unknown", "idempotency_replayed": True,
                "result_may_be_stale": True,
                "message": "Submission was accepted previously but current job state is unavailable.",
            }

        entry = {
            "schema_version": 1,
            "state": "pending",
            "payload_sha256": digest,
            "created_at": int(time.time()),
        }
        _write(path, entry)
        try:
            result = submit()
            if not isinstance(result, dict) or not isinstance(result.get("id"), str):
                raise SubmissionConflict("Submission returned an invalid job identifier.")
            entry["state"] = "complete"
            entry["result"] = result
            _write(path, entry)
            return result
        except Exception:
            # Fail safe: a worker may have been queued. An uncertain result
            # is never silently retried. No secret or full input is journaled.
            raise
