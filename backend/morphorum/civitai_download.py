"""Civitai downloads: persistent queue, bounded concurrency, safe resume and publishing."""
from __future__ import annotations

import hashlib
import json
import os
from .civitai_auth import get_token
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx

from .paths import DATA_DIR, ensure_runtime_dirs
from .settings import load_settings
from .civitai_detail import model_details
from .model_index import scan_models

MAX_BYTES = 40 * 1024 ** 3
RESERVE_BYTES = 256 * 1024 ** 2
MANIFEST = DATA_DIR / "civitai-downloads.json"
_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_RUNNING: set[str] = set()
_INITIALIZED = False
_TERMINAL = {"completed", "failed", "cancelled"}
_PRIVATE = {"url", "expected_hash", "destination", "file_id"}

def _safe_file(filename: str) -> str:
    if not isinstance(filename, str) or "/" in filename or "\\" in filename or filename != filename.strip():
        raise ValueError("Model filename must not include directories.")
    if (not re.fullmatch(r"[\w .()\[\]+-]{1,180}", filename, re.UNICODE)
            or filename in (".", "..") or Path(filename).suffix.lower() != ".safetensors"):
        raise ValueError("A safe .safetensors filename is required.")
    return filename

def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k not in _PRIVATE}

def _part(job: dict[str, Any]) -> Path:
    target = Path(job["destination"])
    return target.with_name(target.name + "." + job["id"] + ".part")

def _save() -> None:
    ensure_runtime_dirs()
    temporary = MANIFEST.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump({"version": 2, "jobs": list(_JOBS.values())[-100:]}, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, MANIFEST)

def _initialize() -> None:
    global _INITIALIZED
    with _LOCK:
        if _INITIALIZED:
            return
        ensure_runtime_dirs()
        if MANIFEST.is_file():
            try:
                data = json.loads(MANIFEST.read_text(encoding="utf-8"))
                for entry in data.get("jobs", [])[:100]:
                    if not isinstance(entry, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(entry.get("id", ""))):
                        continue
                    try:
                        _safe_file(entry["name"])
                        destination = Path(entry["destination"]).resolve()
                        if destination.name != entry["name"] or not destination.parent.is_dir():
                            continue
                        if not str(entry.get("url", "")).startswith("https://civitai.com/api/download/models/"):
                            continue
                        if entry["status"] in ("queued", "downloading"):
                            entry["status"] = "interrupted"
                        entry["bytes"] = _part(entry).stat().st_size if _part(entry).is_file() else 0
                        _JOBS[entry["id"]] = entry
                    except (KeyError, OSError, ValueError):
                        continue
            except (OSError, ValueError, TypeError):
                pass
        _INITIALIZED = True

def list_jobs() -> list[dict[str, Any]]:
    _initialize()
    with _LOCK:
        _dispatch()
        return [_snapshot(j) for j in reversed(list(_JOBS.values()))][:100]

def _check_space(job: dict[str, Any], existing: int = 0) -> None:
    expected = job.get("total_bytes")
    if not isinstance(expected, int) or expected <= 0:
        raise ValueError("Civitai did not provide a usable file size; cannot safely preflight.")
    remaining = max(0, expected - existing)
    if shutil.disk_usage(Path(job["destination"]).parent).free < remaining + RESERVE_BYTES:
        raise ValueError("Insufficient disk space for download and safety reserve.")

def _dispatch() -> None:
    if not load_settings().get("civitai", {}).get("enabled"):
        return
    count = max(1, min(3, int(load_settings()["civitai"].get("concurrent_downloads", 1))))
    for job in list(_JOBS.values()):
        if len(_RUNNING) >= count:
            break
        if job["status"] != "queued" or job["id"] in _RUNNING:
            continue
        _RUNNING.add(job["id"])
        job["status"] = "downloading"
        _save()
        threading.Thread(target=_run, args=(job["id"],), daemon=True, name="civitai-" + job["id"][:8]).start()

def start_download(model_id: int, version_id: int, file_name: str) -> dict[str, Any]:
    _initialize()
    cfg = load_settings()
    if not cfg.get("civitai", {}).get("enabled"):
        raise ValueError("Civitai Hub is disabled.")
    detail = model_details(model_id)
    version = next((v for v in detail["versions"] if v["id"] == version_id), None)
    if not version:
        raise ValueError("Version not available.")
    file = next((f for f in version["files"] if f["name"] == file_name), None)
    if not file or not isinstance(file.get("id"), int) or file["id"] <= 0:
        raise ValueError("Selected Civitai file not available.")
    filename = _safe_file(file_name)
    base = version["base_model"]
    family = "sdxl" if base.startswith("SDXL") else "flux" if base.startswith("Flux.") else "zimage" if base.startswith("ZImage") else None
    kind = "loras" if detail["type"] == "LORA" else "checkpoints" if detail["type"] == "Checkpoint" else None
    if not family or not kind:
        raise ValueError("Unsupported model type or base family.")
    paths = cfg.get("models", {}).get(family, {}).get(kind, [])
    if not paths:
        raise ValueError(f"Configure a {family} {kind} destination in Settings first.")
    root = Path(os.path.expandvars(os.path.expanduser(str(paths[0])))).resolve()
    if not root.is_dir():
        raise ValueError("Configured destination folder does not exist.")
    target = root / filename
    if target.exists():
        raise ValueError("Destination already exists. Never overwriting it.")
    size = file.get("size_kb")
    if not isinstance(size, (int, float)) or not 0 < size * 1024 <= MAX_BYTES:
        raise ValueError("Civitai file size is unavailable or exceeds the 40 GiB limit.")
    digest = str(file.get("sha256") or "").lower()
    if digest and not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid upstream SHA-256.")
    with _LOCK:
        if any(j["destination"] == str(target) and j["status"] not in _TERMINAL for j in _JOBS.values()):
            raise ValueError("That destination is already queued.")
        job_id = uuid.uuid4().hex
        job = {"id": job_id, "name": filename, "model_id": model_id, "version_id": version_id,
               "file_id": file["id"], "family": family, "kind": kind, "status": "queued",
               "bytes": 0, "total_bytes": int(size * 1024), "error": None,
               "url": f"https://civitai.com/api/download/models/{version_id}?type=Model&format=SafeTensor&fileId={file['id']}",
               "expected_hash": digest, "destination": str(target)}
        _check_space(job)
        _JOBS[job_id] = job
        _save()
        _dispatch()
        return _snapshot(job)

def resume_download(job_id: str) -> dict[str, Any]:
    _initialize()
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise KeyError("Download not found.")
        if job["status"] not in ("interrupted", "failed"):
            raise ValueError("Only interrupted or failed downloads can be resumed.")
        if Path(job["destination"]).exists():
            raise ValueError("Destination already exists.")
        _check_space(job, _part(job).stat().st_size if _part(job).exists() else 0)
        job["status"], job["error"] = "queued", None
        _save()
        _dispatch()
        return _snapshot(job)

def retry_download(job_id: str) -> dict[str, Any]:
    _initialize()
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise KeyError("Download not found.")
        if job["status"] not in ("failed", "interrupted"):
            raise ValueError("Only failed or interrupted downloads can be retried.")
        if job_id in _RUNNING:
            raise ValueError("Download still active.")
        if Path(job["destination"]).exists():
            raise ValueError("Destination already exists.")
        _check_space(job)
        _part(job).unlink(missing_ok=True)
        job["bytes"], job["error"], job["status"] = 0, None, "queued"
        _save()
        _dispatch()
        return _snapshot(job)

def cancel_download(job_id: str) -> dict[str, Any]:
    _initialize()
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise KeyError("Download not found.")
        if job["status"] not in _TERMINAL:
            job["status"] = "cancelled"
            if job_id not in _RUNNING:
                _part(job).unlink(missing_ok=True)
            _save()
        return _snapshot(job)

def _run(job_id: str) -> None:
    with _LOCK:
        job = _JOBS[job_id]
    part = _part(job)
    target = Path(job["destination"])
    try:
        existing = part.stat().st_size if part.exists() else 0
        if existing > job["total_bytes"] + 1024 * 1024:
            raise ValueError("Unexpected partial file length; discard and retry.")
        _check_space(job, existing)
        token = get_token()
        headers = {"Accept": "application/octet-stream", "User-Agent": "Morphorum/0.1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if existing:
            headers["Range"] = f"bytes={existing}-"
        with httpx.Client(timeout=httpx.Timeout(60, connect=15), trust_env=False, follow_redirects=True) as client:
            with client.stream("GET", job["url"], headers=headers) as response:
                response.raise_for_status()
                if existing:
                    expected_range = f"bytes {existing}-"
                    actual_range = response.headers.get("content-range", "")
                    if response.status_code != 206 or not actual_range.startswith(expected_range):
                        # A server that ignores Range must not append duplicate bytes.
                        raise ValueError("Civitai server did not honor resume range. Remove partial file and retry.")
                if "text/html" in response.headers.get("content-type", "").lower():
                    raise ValueError("Unexpected HTML instead of model weights.")
                length = response.headers.get("content-length")
                if length and int(length) + existing > MAX_BYTES:
                    raise ValueError("Download exceeds size limit.")
                with part.open("ab" if existing else "xb") as out:
                    count = existing
                    for chunk in response.iter_bytes(1024 * 1024):
                        with _LOCK:
                            if job["status"] == "cancelled" or not load_settings().get("civitai", {}).get("enabled"):
                                job["status"] = "cancelled"
                                break
                        count += len(chunk)
                        if count > MAX_BYTES or count > job["total_bytes"] + 1024 * 1024:
                            raise ValueError("Received more bytes than advertised.")
                        out.write(chunk)
                        with _LOCK:
                            job["bytes"] = count
                    out.flush()
                    os.fsync(out.fileno())
        with _LOCK:
            if job["status"] == "cancelled" or not load_settings().get("civitai", {}).get("enabled"):
                job["status"] = "cancelled"
                part.unlink(missing_ok=True)
                return
            if part.stat().st_size <= 0 or abs(part.stat().st_size - job["total_bytes"]) > 1024 * 1024:
                raise ValueError("Downloaded size differs substantially from advertised size.")
            sha = hashlib.sha256()
            with part.open("rb") as source:
                for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
                    sha.update(chunk)
            if job["expected_hash"] and sha.hexdigest() != job["expected_hash"]:
                part.unlink(missing_ok=True)
                raise ValueError("SHA-256 checksum mismatch.")
            if target.exists():
                raise ValueError("Destination appeared during download; no overwrite.")
            os.link(part, target)
            part.unlink(missing_ok=True)
            job["status"] = "completed"
            job["bytes"] = target.stat().st_size
            job["total_bytes"] = target.stat().st_size
            job["error"] = None
            _save()
        try:
            scan_models()
        except Exception:
            pass
    except Exception as exc:
        with _LOCK:
            if job["status"] != "cancelled":
                job["status"] = "failed"
                if isinstance(exc, httpx.HTTPStatusError):
                    code = exc.response.status_code
                    job["error"] = ("Authentication required or invalid API key (HTTP 401)." if code == 401 else
                                    "Access denied by Civitai (HTTP 403)." if code == 403 else
                                    "Civitai rate limit reached (HTTP 429)." if code == 429 else
                                    f"Civitai HTTP {code} download error.")
                else:
                    job["error"] = "Download failed or connection interrupted." if isinstance(exc, httpx.RequestError) else str(exc)[:180]
    finally:
        if job["status"] == "cancelled":
            part.unlink(missing_ok=True)
        with _LOCK:
            _RUNNING.discard(job_id)
            _save()
            _dispatch()
