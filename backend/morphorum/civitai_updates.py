"""Explicit check for newer Civitai versions of an exactly matched local file."""
from __future__ import annotations

from datetime import datetime
from .civitai_identify import identify_model
from .civitai_detail import model_details
from .civitai_search import CivitaiSearchError
from .model_index import get_model

def _date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

def check_model_update(model_id: str) -> dict:
    identity = identify_model(model_id)
    if not identity.get("found"):
        return {"status": "unidentified", "message": identity.get("message", "Exact Civitai match unavailable."),
                "model_id": model_id, "candidates": []}
    details = model_details(identity["civitai_model_id"])
    installed = next((v for v in details["versions"] if v["id"] == identity["version_id"]), None)
    if not installed:
        return {"status": "unknown", "model_id": model_id, "message": "Installed version absent from Civitai model listing.", "candidates": []}
    record = get_model(model_id)
    installed_date = _date(installed.get("created_at"))
    installed_base = installed.get("base_model")
    candidates = []
    for version in details["versions"]:
        if version["id"] == identity["version_id"]:
            continue
        date = _date(version.get("created_at"))
        if not (installed_date and date and date > installed_date):
            continue
        same_base = version.get("base_model") == installed_base
        compatible_type = record and ((record["kind"] == "loras" and details["type"] == "LORA")
                                      or (record["kind"] == "checkpoints" and details["type"] == "Checkpoint"))
        candidates.append({"version_id": version["id"], "version": version["name"],
                           "base_model": version.get("base_model"), "created_at": version.get("created_at"),
                           "same_base": same_base, "potentially_compatible": bool(same_base and compatible_type),
                           "url": f"https://civitai.com/models/{identity['civitai_model_id']}?modelVersionId={version['id']}"})
    candidates.sort(key=lambda x: x["created_at"], reverse=True)
    return {"status": "newer_available" if candidates else "up_to_date",
            "model_id": model_id, "model_name": identity["name"],
            "installed_version": identity["version"], "installed_version_id": identity["version_id"],
            "installed_base_model": installed_base, "confidence": identity["confidence"],
            "candidates": candidates[:20],
            "message": "Newer versions found; compatibility is advisory." if candidates else "No newer dated version found among returned Civitai versions."}
