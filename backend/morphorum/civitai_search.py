"""Read-only Civitai model discovery. All outbound requests are opt-in."""
from __future__ import annotations

import os
from typing import Any

import httpx

API_URL = "https://civitai.com/api/v1/models"
TYPES = {"Checkpoint", "LORA"}
SORTS = {"Highest Rated", "Most Downloaded", "Most Liked", "Most Discussed", "Most Collected", "Most Images", "Newest", "Oldest"}
PERIODS = {"AllTime", "Year", "Month", "Week", "Day"}
BASE_MODELS = {"SDXL 1.0", "SDXL Turbo", "SDXL Lightning", "Flux.1 D", "Flux.1 S", "ZImageTurbo"}
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class CivitaiSearchError(ValueError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _bounded(value: Any, label: str, limit: int = 120) -> str:
    result = str(value or "").strip()
    if len(result) > limit or any(ord(c) < 32 for c in result):
        raise CivitaiSearchError(f"Invalid {label}.", 422)
    return result


def search_models(
    *, query: str = "", tag: str = "", username: str = "",
    model_type: str = "", base_model: str = "", sort: str = "Most Downloaded",
    period: str = "AllTime", cursor: str = "", limit: int = 20,
    allow_mature: bool = False, client: httpx.Client | None = None,
) -> dict[str, Any]:
    from .settings import load_settings
    if not load_settings().get("civitai", {}).get("enabled", False):
        raise CivitaiSearchError("Civitai Hub is disabled. Enable it in Settings and save.", 403)
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise CivitaiSearchError("Limit must be between 1 and 50.", 422)
    query = _bounded(query, "query")
    tag = _bounded(tag, "tag")
    username = _bounded(username, "username")
    cursor = _bounded(cursor, "cursor", 512)
    if model_type and model_type not in TYPES:
        raise CivitaiSearchError("Unsupported model type.", 422)
    if base_model and base_model not in BASE_MODELS:
        raise CivitaiSearchError("Unsupported base model filter.", 422)
    if sort not in SORTS or period not in PERIODS:
        raise CivitaiSearchError("Unsupported sort or period.", 422)
    cfg = load_settings().get("civitai", {})
    params: dict[str, Any] = {"limit": limit, "sort": sort, "period": period,
                               "nsfw": str(bool(allow_mature and cfg.get("allow_mature", False))).lower()}
    for key, value in (("query", query), ("tag", tag), ("username", username),
                       ("types", model_type), ("baseModels", base_model), ("cursor", cursor)):
        if value:
            params[key] = value
    token = os.environ.get("CIVITAI_API_TOKEN", "").strip()
    headers = {"Accept": "application/json", "User-Agent": "Morphorum/0.1 (optional model discovery)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    owned = client is None
    if owned:
        client = httpx.Client(timeout=15.0, follow_redirects=False, trust_env=False)
    try:
        with client.stream("GET", API_URL, params=params, headers=headers) as response:
            if response.status_code in (401, 403):
                raise CivitaiSearchError("Civitai access denied. Check API authentication.", 502)
            if response.status_code == 429:
                raise CivitaiSearchError("Civitai rate limit reached. Retry later.", 429)
            if response.status_code >= 400:
                raise CivitaiSearchError(f"Civitai search unavailable (HTTP {response.status_code}).", 502)
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise CivitaiSearchError("Civitai returned too much search data.", 502)
                chunks.append(chunk)
        import json
        data = json.loads(b"".join(chunks))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise CivitaiSearchError("Unexpected Civitai search response.", 502)
        items = []
        for item in data["items"][:limit]:
            if not isinstance(item, dict):
                continue
            if not cfg.get("allow_mature", False) and item.get("nsfw"):
                continue
            versions = item.get("modelVersions") if isinstance(item.get("modelVersions"), list) else []
            version = next((v for v in versions if isinstance(v, dict)), {})
            images = version.get("images") if isinstance(version.get("images"), list) else []
            preview = next((im.get("url") for im in images if isinstance(im, dict) and
                            isinstance(im.get("url"), str) and im["url"].startswith("https://")), None)
            creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
            stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
            mid = item.get("id")
            if not isinstance(mid, int) or mid <= 0:
                continue
            items.append({"id": mid, "name": str(item.get("name") or "")[:200],
                          "type": str(item.get("type") or "")[:40],
                          "nsfw": bool(item.get("nsfw")), "creator": str(creator.get("username") or "")[:100],
                          "version_id": version.get("id"), "version_name": str(version.get("name") or "")[:120],
                          "base_model": str(version.get("baseModel") or "")[:100],
                          "thumbnail_url": preview if cfg.get("load_previews", True) else None,
                          "downloads": stats.get("downloadCount", 0),
                          "url": f"https://civitai.com/models/{mid}"})
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        next_cursor = metadata.get("nextCursor")
        return {"items": items, "next_cursor": next_cursor if isinstance(next_cursor, str) and len(next_cursor) <= 512 else None,
                "limit": limit, "count": len(items), "has_more": bool(next_cursor)}
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise CivitaiSearchError("Civitai search timed out or the network is unavailable.", 502) from exc
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, CivitaiSearchError):
            raise
        raise CivitaiSearchError("Civitai returned invalid search data.", 502) from exc
    finally:
        if owned:
            client.close()
