"""C3.3 explicitly synchronized, bounded local Civitai metadata and preview cache."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .paths import CACHE_DIR
from .model_index import get_model
from .settings import load_settings
from .civitai_identify import identify_model
from .civitai_detail import model_details
from .civitai_search import CivitaiSearchError

CACHE_ROOT = CACHE_DIR / "civitai-library"
MAX_IMAGE = 4 * 1024 * 1024

def _directory(model_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", model_id):
        raise CivitaiSearchError("Invalid indexed model ID.", 422)
    return CACHE_ROOT / model_id

def _read(model_id: str):
    record = get_model(model_id)
    if not record:
        raise CivitaiSearchError("Indexed model not found.", 404)
    directory = _directory(model_id)
    manifest = directory / "metadata.json"
    if not manifest.is_file() or manifest.stat().st_size > 256 * 1024:
        return {"synced": False, "model_id": model_id}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"synced": False, "model_id": model_id}
        stat = Path(record["path"]).stat()
        if data.get("size") != stat.st_size or data.get("mtime_ns") != stat.st_mtime_ns:
            return {"synced": False, "model_id": model_id, "stale": True}
        return {k: v for k, v in data.items() if k not in ("size", "mtime_ns")}
    except (OSError, ValueError, TypeError):
        return {"synced": False, "model_id": model_id}

def cached_metadata(model_id: str):
    if not load_settings().get("civitai", {}).get("enabled"):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    data = _read(model_id)
    if data.get("preview_allowed_mature") and not load_settings()["civitai"].get("allow_mature", False):
        data.pop("preview", None)
    if not load_settings()["civitai"].get("load_previews", True):
        data.pop("preview", None)
        data.pop("preview_url", None)
    return data

def cached_catalog(model_ids: list[str]) -> dict:
    """Read bounded cached summaries for manager thumbnails, without network I/O.

    Uses the exact same validity, Civitai preference, and mature-content rules as
    the individual metadata and preview endpoints.
    """
    if not isinstance(model_ids, list) or len(model_ids) > 120:
        raise CivitaiSearchError("Request 0 to 120 indexed model IDs.", 422)
    if any(not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", mid)
           for mid in model_ids):
        raise CivitaiSearchError("Invalid indexed model ID.", 422)
    if not load_settings().get("civitai", {}).get("enabled", False):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    result = {}
    for model_id in dict.fromkeys(model_ids):
        data = cached_metadata(model_id)
        if not data.get("synced"):
            continue
        result[model_id] = {
            "synced": True,
            "name": data.get("name"),
            "version": data.get("version"),
            "base_model": data.get("base_model"),
            "creator": data.get("creator"),
            "synced_at": data.get("synced_at"),
            "trained_words": (data.get("trained_words") or [])[:20],
            "preview": data.get("preview"),
        }
    return {"entries": result}


def _atomic_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".metadata-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(obj, output)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def sync_metadata(model_id: str, *, client: httpx.Client | None = None):
    cfg = load_settings().get("civitai", {})
    if not cfg.get("enabled"):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    record = get_model(model_id)
    if not record:
        raise CivitaiSearchError("Indexed model not found.", 404)
    identity = identify_model(model_id)
    if not identity.get("found"):
        raise CivitaiSearchError("No verified SHA-256 Civitai match. Metadata was not saved.", 404)
    detail = model_details(identity["civitai_model_id"])
    version = next((v for v in detail["versions"] if v["id"] == identity["version_id"]), None)
    if not version:
        raise CivitaiSearchError("The identified model version is unavailable.", 404)
    stat = Path(record["path"]).stat()
    result = {"synced": True, "model_id": model_id, "name": detail["name"],
              "creator": detail["creator"], "version": version["name"],
              "base_model": version["base_model"], "trained_words": version["trained_words"],
              "description": version.get("description") or detail.get("description", ""),
              "civitai_model_id": identity["civitai_model_id"],
              "version_id": identity["version_id"], "url": identity["url"],
              "sha256": identity["sha256"],
              "synced_at": datetime.now(timezone.utc).isoformat(),
              "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    # Image previews are remote content and are only fetched following this explicit action.
    if cfg.get("load_previews", True) and version.get("images"):
        url = version["images"][0]["url"]
        hostname = urlsplit(url).hostname or ""
        if urlsplit(url).scheme == "https" and (hostname == "image.civitai.com" or hostname.endswith(".civitai.com")):
            owned = client is None
            if owned:
                client = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
            try:
                with client.stream("GET", url) as response:
                    if response.status_code == 200 and response.headers.get("content-type", "").lower().split(";")[0] in ("image/jpeg", "image/png", "image/webp"):
                        chunks, count = [], 0
                        for chunk in response.iter_bytes():
                            count += len(chunk)
                            if count > MAX_IMAGE:
                                raise CivitaiSearchError("Preview exceeds 4 MiB limit.", 502)
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        media_type = response.headers["content-type"].lower().split(";")[0]
                        valid_image = (
                            (media_type == "image/jpeg" and data.startswith(b"\\xff\\xd8\\xff")) or
                            (media_type == "image/png" and data.startswith(b"\\x89PNG\\r\\n\\x1a\\n")) or
                            (media_type == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
                        )
                        if not valid_image:
                            result["preview_warning"] = "Civitai returned an invalid preview image."
                        else:
                            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[media_type]
                            directory = _directory(model_id)
                            directory.mkdir(parents=True, exist_ok=True)
                            preview = directory / ("preview" + ext)
                            fd, temporary = tempfile.mkstemp(prefix=".preview-", dir=str(directory))
                            try:
                                with os.fdopen(fd, "wb") as output:
                                    output.write(data)
                                os.replace(temporary, preview)
                            finally:
                                Path(temporary).unlink(missing_ok=True)
                            result["preview"] = preview.name
                            result["preview_allowed_mature"] = bool(cfg.get("allow_mature", False))
            except httpx.RequestError:
                result["preview_warning"] = "Preview download unavailable."
            finally:
                if owned: client.close()
    latest = Path(record["path"]).stat()
    if latest.st_size != stat.st_size or latest.st_mtime_ns != stat.st_mtime_ns:
        raise CivitaiSearchError("Model file changed during synchronization; cache not committed.", 409)
    _atomic_json(_directory(model_id) / "metadata.json", result)
    return {k: v for k, v in result.items() if k not in ("size", "mtime_ns")}

def preview_path(model_id: str) -> Path:
    data = cached_metadata(model_id)
    if not data.get("synced") or not data.get("preview"):
        raise CivitaiSearchError("No cached preview available.", 404)
    path = _directory(model_id) / data["preview"]
    if path.name not in ("preview.jpg", "preview.png", "preview.webp") or not path.is_file():
        raise CivitaiSearchError("Cached preview missing.", 404)
    return path
