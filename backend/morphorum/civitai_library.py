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
    cfg = load_settings()["civitai"]
    if not cfg.get("load_previews", True):
        data.pop("preview", None)
        data.pop("preview_url", None)
        data["preview_status"] = "disabled"
        data["preview_warning"] = "Thumbnail previews are disabled in Settings → Civitai Hub."
    elif data.get("preview_allowed_mature") and not cfg.get("allow_mature", False):
        data.pop("preview", None)
        data["preview_status"] = "filtered"
        data["preview_warning"] = "Cached artwork is hidden by the mature-content setting."
    elif data.get("preview") and not (
            data["preview"] in ("preview.jpg", "preview.png", "preview.webp")
            and (_directory(model_id) / data["preview"]).is_file()):
        data.pop("preview", None)
        data["preview_status"] = "missing"
        data["preview_warning"] = "The cached thumbnail file is missing; sync again."
    elif data.get("preview"):
        data["preview_status"] = "ready"
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
        try:
            data = cached_metadata(model_id)
        except CivitaiSearchError as exc:
            if exc.status == 404:  # An indexed file disappeared during a rescan.
                continue
            raise
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
            "preview_status": data.get("preview_status", "unavailable"),
            "preview_warning": data.get("preview_warning"),
            "preview_source": data.get("preview_source"),
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


def _trusted_preview_url(url: str) -> bool:
    """Reject arbitrary hosts, schemes, credentials and unsupported URL forms."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and parsed.port in (None, 443)
                and not parsed.username and not parsed.password and
                bool(host) and (host == "civitai.com" or host.endswith(".civitai.com")))
    except ValueError:
        return False


def _fetch_preview_image(client: httpx.Client, url: str) -> tuple[str, bytes]:
    """Bounded still-image fetch with explicitly checked same-provider redirects."""
    target = url
    for _ in range(3):
        if not _trusted_preview_url(target):
            raise CivitaiSearchError("Civitai preview redirected to an untrusted host.", 502)
        with client.stream("GET", target, headers={"Accept": "image/webp, image/png, image/jpeg",
                                                   "User-Agent": "Morphorum/0.1 (opt-in thumbnail sync)"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if not location:
                    raise CivitaiSearchError("Civitai image redirect has no destination.", 502)
                from urllib.parse import urljoin
                target = urljoin(target, location)
                continue
            if response.status_code != 200:
                raise CivitaiSearchError(
                    f"Civitai image server returned HTTP {response.status_code}.", 502)
            media = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if media not in ("image/jpeg", "image/png", "image/webp"):
                raise CivitaiSearchError(
                    "Civitai returned an unsupported thumbnail image format.", 502)
            total = 0
            chunks = []
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE:
                    raise CivitaiSearchError("Civitai thumbnail exceeds 4 MiB.", 502)
                chunks.append(chunk)
        data = b"".join(chunks)
        valid = (
            (media == "image/jpeg" and data.startswith(b"\xff\xd8\xff")) or
            (media == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
            (media == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        )
        if not valid:
            raise CivitaiSearchError("Civitai returned invalid thumbnail image data.", 502)
        return media, data
    raise CivitaiSearchError("Too many Civitai image redirects.", 502)


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
    # Keep a verified older preview when resyncing this exact file/version,
    # even if today's Civitai image CDN is unavailable.
    previous = _read(model_id)
    if (previous.get("synced") and previous.get("sha256") == identity["sha256"]
            and previous.get("version_id") == identity["version_id"]):
        filename = previous.get("preview")
        if filename in {"preview.jpg", "preview.png", "preview.webp"} and (
                _directory(model_id) / filename).is_file():
            result["preview"] = filename
            result["preview_allowed_mature"] = previous.get("preview_allowed_mature", False)

    # All remote downloads remain explicitly user-triggered and image-only.
    # Some Civitai versions have no example images. A safe still from another
    # version of the *same verified model* is useful as representative artwork.
    if not cfg.get("load_previews", True):
        result["preview_warning"] = "Thumbnail previews are disabled in Settings → Civitai Hub."
    else:
        candidates = [(image, False) for image in (version.get("images") or [])]
        for other in detail.get("versions", []):
            if other.get("id") == identity["version_id"]:
                continue
            candidates.extend((image, True) for image in (other.get("images") or []))
            if len(candidates) >= 24:
                break
        candidates = candidates[:24]
        # Bounded: inspect at most 24 image candidates and download at most 6.
        attempted = 0
        last_reason = ""
        seen = set()
        owned = client is None
        if candidates and owned:
            client = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
        try:
            for image, is_other_version in candidates:
                if attempted >= 6:
                    break
                if not isinstance(image, dict) or not isinstance(image.get("url"), str):
                    continue
                url = image["url"]
                if url in seen or not _trusted_preview_url(url):
                    continue
                seen.add(url)
                attempted += 1
                try:
                    media, data = _fetch_preview_image(client, url)
                except CivitaiSearchError as exc:
                    last_reason = str(exc)
                    continue
                except (httpx.RequestError, httpx.TimeoutException):
                    last_reason = "Civitai image server could not be reached."
                    continue
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[media]
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
                result["preview_allowed_mature"] = bool(
                    detail.get("mature") or image.get("mature"))
                result["preview_source"] = (
                    "same_model_other_version" if is_other_version else "installed_version")
                result.pop("preview_warning", None)
                break
        finally:
            if owned and client is not None:
                client.close()
        if not result.get("preview"):
            result["preview_warning"] = (
                last_reason or
                ("No allowed still-image previews are available for this Civitai model."
                 if not candidates else "No usable Civitai thumbnail could be downloaded.")
            )
        elif last_reason and result.get("preview_source") is None:
            # Previous verified art was kept after this resync's remote failure.
            result["preview_warning"] = (
                "Existing cached thumbnail retained; " + last_reason
            )
    result["preview_status"] = "ready" if result.get("preview") else (
        "disabled" if not cfg.get("load_previews", True) else "unavailable")
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
