"""C2.1 opt-in, single-worker Civitai downloads into configured model directories."""
from __future__ import annotations
import hashlib
import os
import re
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import httpx
from .settings import load_settings
from .civitai_detail import model_details
from .model_index import scan_models

_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_QUEUE: deque[str] = deque()
_WORKER: threading.Thread | None = None
MAX_BYTES = 40 * 1024 ** 3

def _safe_file(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    if not re.fullmatch(r"[\w .()\[\]+-]{1,180}", name, re.UNICODE) or name in (".", ".."):
        raise ValueError("Unsafe model filename.")
    if Path(name).suffix.lower() != ".safetensors":
        raise ValueError("C2.1 accepts .safetensors files only.")
    return name

def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in ("url", "expected_hash", "destination")}

def list_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [_snapshot(job) for job in reversed(list(_JOBS.values()))][:100]

def start_download(model_id: int, version_id: int, file_name: str) -> dict[str, Any]:
    global _WORKER
    cfg = load_settings()
    if not cfg.get("civitai", {}).get("enabled"):
        raise ValueError("Civitai Hub is disabled.")
    detail = model_details(model_id)
    version = next((v for v in detail["versions"] if v["id"] == version_id), None)
    if not version:
        raise ValueError("Version not available.")
    file = next((f for f in version["files"] if f["name"] == file_name), None)
    if not file:
        raise ValueError("File not available.")
    if not isinstance(file.get("id"), int) or file["id"] <= 0:
        raise ValueError("Missing Civitai file ID.")
    filename = _safe_file(file_name)
    base = version["base_model"]
    family = "sdxl" if base.startswith("SDXL") else "flux" if base.startswith("Flux.") else "zimage" if base.startswith("ZImage") else None
    kind = "loras" if detail["type"] == "LORA" else "checkpoints" if detail["type"] == "Checkpoint" else None
    if not family or not kind:
        raise ValueError("Unsupported model type/base family.")
    roots = cfg.get("models", {}).get(family, {}).get(kind, [])
    if not roots:
        raise ValueError(f"Configure a {family} {kind} destination in Settings first.")
    root = Path(os.path.expandvars(os.path.expanduser(str(roots[0])))).resolve()
    if not root.is_dir():
        raise ValueError("Configured destination folder does not exist.")
    destination = root / filename
    if destination.exists():
        raise ValueError("File already exists. C2.1 will never overwrite it.")
    size_kb = file.get("size_kb")
    if isinstance(size_kb, (int,float)) and size_kb * 1024 > MAX_BYTES:
        raise ValueError("File exceeds 40 GiB safety limit.")
    sha = str(file.get("sha256") or "").lower()
    if sha and not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid upstream SHA-256.")
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "name": filename, "model_id": model_id, "version_id": version_id,
           "family": family, "kind": kind, "status": "queued", "bytes": 0,
           "total_bytes": int(size_kb * 1024) if isinstance(size_kb, (int,float)) else None,
           "error": None, "url": f"https://civitai.com/api/download/models/{version_id}?type=Model&format=SafeTensor&fileId={file['id']}",
           "expected_hash": sha, "destination": str(destination)}
    with _LOCK:
        _JOBS[job_id] = job
        _QUEUE.append(job_id)
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_worker, daemon=True, name="civitai-download-worker")
            _WORKER.start()
    return _snapshot(job)

def cancel_download(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise KeyError("Download not found.")
        if job["status"] in ("queued", "downloading"):
            job["status"] = "cancelled"
        return _snapshot(job)

def _worker() -> None:
    while True:
        with _LOCK:
            if not _QUEUE:
                return
            job = _JOBS[_QUEUE.popleft()]
            if job["status"] == "cancelled":
                continue
            job["status"] = "downloading"
        target = Path(job["destination"])
        part = target.with_name(target.name + "." + job["id"] + ".part")
        digest = hashlib.sha256()
        try:
            token = os.environ.get("CIVITAI_API_TOKEN", "").strip()
            headers = {"User-Agent": "Morphorum/0.1", "Accept": "application/octet-stream"}
            if token:
                headers["Authorization"] = "Bearer " + token
            with httpx.Client(timeout=httpx.Timeout(40, connect=15), follow_redirects=True, trust_env=False) as client:
                with client.stream("GET", job["url"], headers=headers) as response:
                    response.raise_for_status()
                    if "text/html" in response.headers.get("content-type", "").lower():
                        raise ValueError("Civitai returned HTML instead of model weights.")
                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_BYTES:
                        raise ValueError("Download exceeds size limit.")
                    with part.open("xb") as out:
                        total = 0
                        for chunk in response.iter_bytes(1024 * 1024):
                            with _LOCK:
                                if job["status"] == "cancelled" or not load_settings().get("civitai", {}).get("enabled"):
                                    job["status"] = "cancelled"
                                    break
                            total += len(chunk)
                            if total > MAX_BYTES:
                                raise ValueError("Download exceeds size limit.")
                            out.write(chunk)
                            digest.update(chunk)
                            with _LOCK:
                                job["bytes"] = total
                        else:
                            if job["expected_hash"] and digest.hexdigest() != job["expected_hash"]:
                                raise ValueError("SHA-256 mismatch. Download discarded.")
                            with _LOCK:
                                if job["status"] != "cancelled":
                                    if target.exists():
                                        raise ValueError("Destination appeared during download; refusing overwrite.")
                                    os.link(part, target)
                                    job["status"] = "completed"
            if job["status"] == "completed":
                try:
                    scan_models()
                except Exception:
                    pass
        except Exception as exc:
            with _LOCK:
                job["status"] = "failed"
                job["error"] = str(exc)[:200] if not token or token not in str(exc) else "Download failed."
        finally:
            part.unlink(missing_ok=True)
