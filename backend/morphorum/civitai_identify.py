"""Explicit Civitai SHA-256 identification for indexed local models."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import httpx
from .paths import CACHE_DIR
from .model_index import get_model
from .settings import load_settings
from .civitai_auth import get_token
from .civitai_search import CivitaiSearchError, MAX_RESPONSE_BYTES

def _hash(path: Path, model_id: str) -> str:
    stat = path.stat()
    cache = CACHE_DIR / "civitai-identify" / f"{model_id}.json"
    try:
        if cache.is_file() and cache.stat().st_size < 2048:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("size") == stat.st_size and data.get("mtime_ns") == stat.st_mtime_ns and re.fullmatch(r"[a-f0-9]{64}", data.get("digest", "")):
                return data["digest"]
    except (OSError, ValueError, TypeError):
        pass
    sha = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    now = path.stat()
    if now.st_size != stat.st_size or now.st_mtime_ns != stat.st_mtime_ns:
        raise CivitaiSearchError("Model changed during hashing. Rescan and retry.", 409)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "digest": sha.hexdigest()}), encoding="utf-8")
    return sha.hexdigest()

def identify_model(model_id: str, *, client: httpx.Client | None = None) -> dict:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    record = get_model(model_id)
    if not record or record.get("kind") not in ("loras", "checkpoints"):
        raise CivitaiSearchError("Indexed model not found.", 404)
    path = Path(record["path"])
    if not path.is_file():
        raise CivitaiSearchError("Indexed file missing. Rescan your models.", 404)
    try:
        digest = _hash(path, model_id)
    except OSError as exc:
        raise CivitaiSearchError("Unable to read the selected model.", 500) from exc
    headers = {"Accept": "application/json", "User-Agent": "Morphorum/0.1"}
    token = get_token()
    if token: headers["Authorization"] = "Bearer " + token
    owned = client is None
    if owned: client = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
    try:
        with client.stream("GET", "https://civitai.com/api/v1/model-versions/by-hash/" + digest.upper(), headers=headers) as response:
            if response.status_code == 404:
                return {"found": False, "sha256": digest, "model_id": model_id, "message": "No exact SHA-256 match found."}
            if response.status_code == 429:
                raise CivitaiSearchError("Civitai rate limit reached.", 429)
            if response.status_code >= 400:
                raise CivitaiSearchError(f"Civitai identification unavailable (HTTP {response.status_code}).", 502)
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES: raise CivitaiSearchError("Civitai metadata exceeds limit.", 502)
                chunks.append(chunk)
        data = json.loads(b"".join(chunks))
        if not isinstance(data, dict) or not isinstance(data.get("id"), int) or not isinstance(data.get("modelId"), int):
            raise CivitaiSearchError("Invalid Civitai identity response.", 502)
        model = data.get("model") if isinstance(data.get("model"), dict) else {}
        if model.get("nsfw") and not load_settings()["civitai"].get("allow_mature", False):
            return {"found": False, "sha256": digest, "model_id": model_id, "message": "Exact match hidden by mature-content setting."}
        remote_model = data["modelId"]
        return {"found": True, "confidence": "Exact SHA-256 file match",
                "sha256": digest, "model_id": model_id, "civitai_model_id": remote_model,
                "version_id": data["id"], "name": str(model.get("name") or "")[:200],
                "version": str(data.get("name") or "")[:150],
                "base_model": str(data.get("baseModel") or "")[:100],
                "url": f"https://civitai.com/models/{remote_model}?modelVersionId={data['id']}"}
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        raise CivitaiSearchError("Civitai identification network error.", 502) from exc
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, CivitaiSearchError): raise
        raise CivitaiSearchError("Invalid response from Civitai.", 502) from exc
    finally:
        if owned: client.close()
