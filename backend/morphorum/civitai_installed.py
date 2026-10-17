"""Offline mapping of Civitai model versions to verified local indexed files."""
from __future__ import annotations

from .model_index import list_models
from .civitai_library import _read
from .settings import load_settings
from .civitai_search import CivitaiSearchError

def installed_versions(model_id: int) -> dict:
    if not load_settings().get("civitai", {}).get("enabled"):
        raise CivitaiSearchError("Civitai Hub is disabled.", 403)
    if not isinstance(model_id, int) or model_id <= 0:
        raise CivitaiSearchError("Invalid Civitai model ID.", 422)
    matches = []
    for record in list_models(limit=2000):
        cached = _read(record["id"])
        if not cached.get("synced") or cached.get("civitai_model_id") != model_id:
            continue
        matches.append({"id": record["id"], "name": record["name"],
                        "family": record["family"], "kind": record["kind"],
                        "version_id": cached.get("version_id"),
                        "base_model": cached.get("base_model"),
                        "trained_words": cached.get("trained_words", [])[:20]})
    return {"model_id": model_id, "installed": matches}
