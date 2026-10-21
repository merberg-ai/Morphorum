"""PS1.4: Project-owned, versioned Prompt Studio drafts.

Drafts are separate from project.json and never modify project render data.
A stored baseline allows the browser to refuse an unsafe automatic rebase.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import animation_projects as projects

FORMAT = "morphorum.prompt-studio-draft"
VERSION = 1
MAX_DRAFTS = 30
MAX_DRAFT_BYTES = 8 * 1024 * 1024
DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
DRAFT_FILE = re.compile(r"^prompt_studio/drafts/([0-9a-f]{32})\.json$")


class PromptDraftError(ValueError):
    pass


class PromptDraftConflict(PromptDraftError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _folder(project_id: str) -> Path:
    # A project must be real before drafts may be read, written or listed.
    projects.load_animation_project(project_id)
    root = projects.animation_project_directory(project_id)
    relative = root / "prompt_studio"
    target = relative / "drafts"
    if root.is_symlink() or relative.is_symlink() or target.is_symlink():
        raise PromptDraftError("Prompt Studio draft directory must not be a symbolic link.")
    return target


def _file(project_id: str, draft_id: str) -> Path:
    if not isinstance(draft_id, str) or not DRAFT_ID.fullmatch(draft_id):
        raise PromptDraftError("Invalid Prompt Studio draft ID.")
    return _folder(project_id) / (draft_id + ".json")


def _validate_tracks(value: Any, max_frames: int, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"positive", "negative"}:
        raise PromptDraftError(f"{label} requires exactly two prompt lanes.")
    normalized = {}
    total_chars = 0
    for lane in ("positive", "negative"):
        track = value[lane]
        if not isinstance(track, dict) or track.get("kind") != "prompt" or (
                track.get("interpolation") not in ("blend", "hold")):
            raise PromptDraftError(f"{label}.{lane} has an invalid interpolation or kind.")
        points = track.get("keyframes")
        if not isinstance(points, list) or not 1 <= len(points) <= 3000:
            raise PromptDraftError(f"{label}.{lane} requires 1–3000 keyframes.")
        previous = -1
        entries = []
        for point in points:
            if not isinstance(point, dict):
                raise PromptDraftError("Prompt keyframes must be objects.")
            frame = point.get("frame")
            text = point.get("value")
            if type(frame) is not int or frame <= previous or frame >= max_frames or (
                    not isinstance(text, str) or len(text) > 32768):
                raise PromptDraftError(f"{label}.{lane} has invalid, unordered, or oversized keyframes.")
            total_chars += len(text)
            if total_chars > 4_000_000:
                raise PromptDraftError("Prompt text total exceeds 4,000,000 characters.")
            entries.append({"frame": frame, "value": text})
            previous = frame
        if entries[0]["frame"] != 0:
            raise PromptDraftError(f"{label}.{lane} must begin at frame zero.")
        normalized[lane] = {
            "kind": "prompt",
            "interpolation": track["interpolation"],
            "keyframes": entries,
        }
    return normalized


def _validate_composer(value: Any, max_frames: int) -> dict[str, Any]:
    """PS3 optional composer; existing version-one drafts remain readable."""
    if value is None:
        return {"schema_version": 1, "blocks": []}
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or
            value["schema_version"] != 1 or not isinstance(value.get("blocks"), list) or
            len(value["blocks"]) > 100):
        raise PromptDraftError("Unsupported Prompt Studio composer version or block count.")
    ids: set[str] = set()
    output: list[dict[str, Any]] = []
    for raw in value["blocks"]:
        if not isinstance(raw, dict):
            raise PromptDraftError("Composer block must be an object.")
        ident = raw.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", ident) or ident in ids:
            raise PromptDraftError("Composer block IDs must be unique and safe.")
        ids.add(ident)
        scope, lane, kind, placement = (raw.get(k) for k in ("scope", "lane", "kind", "placement"))
        if (scope not in ("global", "frame") or lane not in ("positive", "negative")
                or kind not in ("text", "lora") or placement not in ("before", "after")
                or type(raw.get("enabled")) is not bool):
            raise PromptDraftError("Invalid composer block type, scope or placement.")
        frame = raw.get("frame")
        if scope == "global":
            if frame is not None:
                raise PromptDraftError("Global composer block cannot reference a frame.")
        elif type(frame) is not int or not 0 <= frame < max_frames:
            raise PromptDraftError("Composer scene frame is outside the project.")
        label = raw.get("label", "")
        if not isinstance(label, str) or len(label) > 120:
            raise PromptDraftError("Composer label must contain at most 120 characters.")
        block = {"id": ident, "scope": scope, "frame": frame, "lane": lane,
                 "kind": kind, "placement": placement, "enabled": raw["enabled"], "label": label}
        if kind == "text":
            if not isinstance(raw.get("text"), str) or len(raw["text"]) > 32768:
                raise PromptDraftError("Composer text is invalid or oversized.")
            block["text"] = raw["text"]
        else:
            import math
            name, weight = raw.get("name"), raw.get("weight")
            triggers = raw.get("triggers")
            if (lane != "positive" or not isinstance(name, str) or not name.strip() or
                    len(name) > 140 or re.search(r"[:<>\r\n]", name) or
                    type(weight) not in (float, int) or not math.isfinite(weight) or
                    not -4 <= weight <= 4 or raw.get("family") not in ("sdxl", "flux", "zimage") or
                    not isinstance(raw.get("model_id"), str) or len(raw["model_id"]) > 128 or
                    not isinstance(triggers, list) or len(triggers) > 24 or
                    any(not isinstance(t, str) or len(t) > 160 or "\n" in t or "\r" in t
                        for t in triggers)):
                raise PromptDraftError("Invalid LoRA directive, trigger word or model family.")
            block.update({"model_id": raw["model_id"], "name": name,
                          "weight": float(weight), "family": raw["family"], "triggers": list(triggers)})
        output.append(block)
    return {"schema_version": 1, "blocks": output}



def _validate_ai_provenance(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            "provider", "model", "created_at", "mode", "scene_count", "family", "profile"}:
        raise PromptDraftError("Invalid AI storyboard provenance.")
    from .prompt_studio_profiles import PROFILE_IDS
    if (value.get("provider") != "ollama" or value.get("mode") not in ("create", "refine")
            or value.get("family") not in ("sdxl", "flux", "zimage") or
            value.get("profile") not in ("ps4-generic-v1", PROFILE_IDS.get(value.get("family"))) or
            type(value.get("scene_count")) is not int or not 1 <= value["scene_count"] <= 16 or
            not isinstance(value.get("model"), str) or not 1 <= len(value["model"]) <= 160 or
            not isinstance(value.get("created_at"), str) or len(value["created_at"]) > 64):
        raise PromptDraftError("AI provenance contains unsupported values.")
    return dict(value)


def validate_draft(value: Any, project_id: str, *, draft_id: str | None = None,
                   stored: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise PromptDraftError("This is not a Morphorum Prompt Studio draft.")
    if type(value.get("schema_version")) is not int or value["schema_version"] != VERSION:
        raise PromptDraftError("Unsupported Prompt Studio draft version; upgrade before importing.")
    if value.get("project_id") != project_id:
        raise PromptDraftError("Prompt Studio draft belongs to a different project.")
    if draft_id is not None and value.get("draft_id") != draft_id:
        raise PromptDraftError("Prompt Studio draft ID does not match its filename.")
    name = value.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise PromptDraftError("Draft name must be between 1 and 120 characters.")
    context = value.get("project_context")
    if not isinstance(context, dict) or not isinstance(context.get("model"), dict):
        raise PromptDraftError("Draft project/model context is missing.")
    frames = context.get("max_frames")
    fps = context.get("fps")
    if type(frames) is not int or not 1 <= frames <= 1_000_000 or (
            type(fps) not in (float, int) or not 1 <= fps <= 240):
        raise PromptDraftError("Draft frame count or frame rate is invalid.")
    model = context["model"]
    if not all(isinstance(model.get(k, ""), str) and len(model.get(k, "")) <= 1000
               for k in ("model_id", "family", "variant")):
        raise PromptDraftError("Draft model reference is invalid.")
    original = _validate_tracks(value.get("original_tracks"), frames, "original_tracks")
    edited = _validate_tracks(value.get("prompt_tracks"), frames, "prompt_tracks")
    normalized = {
        "format": FORMAT,
        "schema_version": VERSION,
        "project_id": project_id,
        "name": name.strip(),
        "project_context": {
            "model": {k: model.get(k, "") for k in ("model_id", "family", "variant")},
            "max_frames": frames,
            "fps": float(fps),
            "start_mode": str(context.get("start_mode") or "prompt")[:32],
            "source_image_name": str(context.get("source_image_name") or "")[:255],
        },
        "original_tracks": original,
        "prompt_tracks": edited,
        "composer": _validate_composer(value.get("composer"), frames),
        "ai_provenance": _validate_ai_provenance(value.get("ai_provenance")),
    }
    if stored:
        identifier = value.get("draft_id")
        if not isinstance(identifier, str) or not DRAFT_ID.fullmatch(identifier):
            raise PromptDraftError("Saved draft ID is invalid.")
        if not all(isinstance(value.get(k), str) and len(value[k]) <= 64
                   for k in ("created_at", "updated_at")):
            raise PromptDraftError("Saved draft timestamps are invalid.")
        normalized.update({
            "draft_id": identifier,
            "created_at": value["created_at"],
            "updated_at": value["updated_at"],
        })
    return normalized


def _load(path: Path, project_id: str) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DRAFT_BYTES:
        raise PromptDraftError("Draft is missing, unsafe, or too large.")
    raw = path.read_bytes()
    try:
        saved = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PromptDraftError("Saved Prompt Studio draft is invalid JSON.") from exc
    value = validate_draft(saved, project_id, draft_id=path.stem, stored=True)
    return value, '"' + hashlib.sha256(raw).hexdigest() + '"'


def read_draft(project_id: str, draft_id: str) -> tuple[dict, str]:
    with projects._PROJECT_SAVE_LOCK:
        return _load(_file(project_id, draft_id), project_id)


def list_drafts(project_id: str) -> list[dict]:
    with projects._PROJECT_SAVE_LOCK:
        folder = _folder(project_id)
        if not folder.is_dir():
            return []
        drafts = []
        for file in folder.iterdir():
            if file.suffix != ".json" or not DRAFT_ID.fullmatch(file.stem):
                raise PromptDraftError("Unexpected file in the Prompt Studio draft directory.")
            value, etag = _load(file, project_id)
            drafts.append({
                "draft_id": value["draft_id"], "name": value["name"],
                "created_at": value["created_at"], "updated_at": value["updated_at"],
                "etag": etag,
            })
        if len(drafts) > MAX_DRAFTS:
            raise PromptDraftError("Too many saved Prompt Studio drafts.")
        return sorted(drafts, key=lambda item: (item["updated_at"], item["draft_id"]), reverse=True)


def _write(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_DRAFT_BYTES:
        raise PromptDraftError("Prompt Studio draft exceeds the 8 MiB limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return '"' + hashlib.sha256(data).hexdigest() + '"'


def create_draft(project_id: str, payload: dict) -> tuple[dict, str]:
    with projects._PROJECT_SAVE_LOCK:
        data = validate_draft(payload, project_id)
        folder = _folder(project_id)
        if folder.exists() and (len(list_drafts(project_id)) >= MAX_DRAFTS):
            raise PromptDraftError("Project has reached the limit of 30 Studio drafts.")
        identifier = uuid.uuid4().hex
        now = _now()
        data.update({"draft_id": identifier, "created_at": now, "updated_at": now})
        etag = _write(folder / (identifier + ".json"), data)
        return data, etag


def update_draft(project_id: str, draft_id: str, payload: dict,
                 expected_etag: str | None) -> tuple[dict, str]:
    if expected_etag is None:
        raise PromptDraftError("Saving a Studio draft requires its last loaded ETag.")
    with projects._PROJECT_SAVE_LOCK:
        path = _file(project_id, draft_id)
        current, etag = _load(path, project_id)
        if etag != expected_etag:
            raise PromptDraftConflict("Draft changed in another browser. Reload it before saving.")
        edited = validate_draft(payload, project_id, draft_id=draft_id
                                if "draft_id" in payload else None)
        edited.update({"draft_id": draft_id, "created_at": current["created_at"],
                       "updated_at": _now()})
        new_etag = _write(path, edited)
        return edited, new_etag


def delete_draft(project_id: str, draft_id: str, expected_etag: str | None) -> None:
    if expected_etag is None:
        raise PromptDraftError("Deleting a Studio draft requires its last loaded ETag.")
    with projects._PROJECT_SAVE_LOCK:
        path = _file(project_id, draft_id)
        _, etag = _load(path, project_id)
        if etag != expected_etag:
            raise PromptDraftConflict("Draft changed in another browser. Reload it before deleting.")
        path.unlink()


def draft_files(project_id: str) -> dict[str, Path]:
    """Validate all named draft files for archive export and Save As."""
    with projects._PROJECT_SAVE_LOCK:
        output = {}
        folder = _folder(project_id)
        if not folder.is_dir():
            return output
        listing = list_drafts(project_id)
        for draft in listing:
            identifier = draft["draft_id"]
            output[f"prompt_studio/drafts/{identifier}.json"] = folder / (identifier + ".json")
        return output


def rewrite_draft_project(raw: bytes, old_id: str, new_id: str) -> bytes:
    """Rewrite project ownership when Save As creates an independent folder."""
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PromptDraftError("Cannot copy malformed Studio draft.") from exc
    validated = validate_draft(payload, old_id, stored=True)
    validated["project_id"] = new_id
    return (json.dumps(validated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
