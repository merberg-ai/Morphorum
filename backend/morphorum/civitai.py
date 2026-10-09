from __future__ import annotations

"""Optional, user-triggered Civitai metadata lookups for indexed LoRA files."""

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from .lora_inspector import LoRAInspectionError, _sidecar, _words
from .model_index import get_model
from .paths import CACHE_DIR

CIVITAI_API = "https://civitai.com/api/v1/model-versions"
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
MAX_CACHE_BYTES = 256 * 1024
MAX_DESC_LENGTH = 5000


class CivitaiLookupError(ValueError):
    pass


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skipped += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skipped = max(0, self.skipped - 1)

    def handle_data(self, data):
        if not self.skipped and sum(len(x) for x in self.parts) < MAX_DESC_LENGTH:
            self.parts.append(data)


def _plain_html(text: Any) -> str:
    parser = _HTMLText()
    try:
        parser.feed(str(text or "")[:30000])
    except (ValueError, TypeError):
        return ""
    normalized = " ".join(" ".join(parser.parts).split())
    return re.sub(r"\s+([.,!?;:])", r"\1", normalized)[:MAX_DESC_LENGTH]


def _local_info(path: Path) -> dict[str, Any]:
    info, _ = _sidecar(path)
    version = info.get("modelVersionId") or info.get("model_version_id")
    nested = info.get("modelVersion") or {}
    if not version and isinstance(nested, dict):
        version = nested.get("id")
    try:
        version = int(version)
    except (ValueError, TypeError):
        version = None
    return {"version_id": version if version and version > 0 else None}


def _digest_cache(model_id: str) -> Path:
    # model_id is the stable (opaque) indexed ID; never use arbitrary user paths.
    return CACHE_DIR / "lora-civitai" / f"hash-{model_id}.json"


def _sha256(model_id: str, path: Path) -> str:
    stat = path.stat()
    cache_path = _digest_cache(model_id)
    try:
        if cache_path.is_file() and cache_path.stat().st_size < MAX_CACHE_BYTES:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (cached.get("size") == stat.st_size and
                    cached.get("mtime_ns") == stat.st_mtime_ns and
                    re.fullmatch(r"[0-9a-f]{64}", str(cached.get("sha256") or ""))):
                return cached["sha256"]
    except (OSError, ValueError, TypeError):
        pass

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    # Don't cache the digest of a file if it was replaced during hashing.
    if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
        raise CivitaiLookupError("LoRA file changed during hashing. Retry the lookup.")
    result = digest.hexdigest()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": result,
        }), encoding="utf-8")
    except OSError:
        pass
    return result


def _get_version(url: str, *, client: httpx.Client) -> dict[str, Any] | None:
    # URL is created inside this module from sanitized digest/numeric IDs.
    try:
        response = client.get(url, follow_redirects=False)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise CivitaiLookupError("Civitai response exceeded the metadata size limit.")
        data = response.json()
        if not isinstance(data, dict):
            raise CivitaiLookupError("Civitai did not return a model version object.")
        return data
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError,
            httpx.DecodingError, ValueError) as exc:
        if isinstance(exc, CivitaiLookupError):
            raise
        raise CivitaiLookupError(f"Civitai lookup failed: {type(exc).__name__}: {str(exc)[:180]}") from exc


def _summarize(data: dict[str, Any], *, source: str, digest: str) -> dict[str, Any]:
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    mid = data.get("modelId")
    vid = data.get("id")
    try:
        mid = int(mid)
        vid = int(vid)
        if mid <= 0 or vid <= 0:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise CivitaiLookupError("Civitai returned missing or invalid model/version IDs.") from exc
    return {
        "source": source,
        "confidence": ("exact SHA-256 file match" if source == "sha256" else "sidecar version ID (not hash-verified)"),
        "sha256": digest,
        "model_id": mid, "version_id": vid,
        "url": f"https://civitai.com/models/{mid}?modelVersionId={vid}",
        "model_name": str(model.get("name") or "")[:200],
        "version_name": str(data.get("name") or "")[:200],
        "creator": str((data.get("creator") or {}).get("username") or "")[:120] if isinstance(data.get("creator"), dict) else "",
        "base_model": str(data.get("baseModel") or "")[:200],
        "type": str(model.get("type") or "")[:100],
        "trained_words": _words(data.get("trainedWords")),
        "description_text": _plain_html(data.get("description")),
        "model_nsfw": bool(model.get("nsfw", False)),
    }


def lookup_civitai(model_id: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Look up exact hash first, then sidecar modelVersionId on a 404.

    Only called by an explicit user action. The API receives the file hash,
    not image prompts, local paths, or LoRA file contents.
    """
    record = get_model(model_id)
    if not record or record.get("kind") != "loras":
        raise CivitaiLookupError("Indexed LoRA not found.")
    path = Path(str(record.get("path") or ""))
    if not path.is_file():
        raise CivitaiLookupError("LoRA file no longer exists; rescan Models.")

    try:
        sha = _sha256(model_id, path)
    except OSError as exc:
        raise CivitaiLookupError(f"Unable to hash LoRA: {exc}") from exc

    owned_client = client is None
    if owned_client:
        client = httpx.Client(timeout=12.0, trust_env=False, headers={
            "User-Agent": "Morphorum/0.1 (optional local LoRA metadata lookup)",
            "Accept": "application/json",
        })
    try:
        version = _get_version(f"{CIVITAI_API}/by-hash/{sha.upper()}", client=client)
        source = "sha256"
        if version is None:
            sidecar_version = _local_info(path)["version_id"]
            if sidecar_version:
                version = _get_version(f"{CIVITAI_API}/{sidecar_version}", client=client)
                source = "sidecar_version_id"
        if version is None:
            return {
                "found": False, "sha256": sha,
                "message": "No matching Civitai version found by SHA-256 or local sidecar version ID.",
            }
        info = _summarize(version, source=source, digest=sha)
        return {"found": True, **info}
    finally:
        if owned_client:
            client.close()
