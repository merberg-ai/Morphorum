from __future__ import annotations

import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .model_index import list_models
from .schedules import ScheduleError

LORA_TAG = re.compile(
    r"<lora\s*:\s*([^:>]+?)\s*:\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*>",
    re.IGNORECASE,
)


class LoRAError(ScheduleError):
    pass


def parse_lora_tags(text: Any) -> tuple[str, list[dict[str, Any]]]:
    source = str(text or "")
    directives: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        name = str(match.group(1) or "").strip()
        if not name:
            raise LoRAError("LoRA tag name cannot be empty.")
        try:
            weight = float(match.group(2))
        except (TypeError, ValueError) as exc:
            raise LoRAError(f"Invalid LoRA weight for '{name}'.") from exc
        if not math.isfinite(weight):
            raise LoRAError(f"LoRA weight for '{name}' must be finite.")
        directives.append({"name": name, "weight": weight})
        return ""

    cleaned = LORA_TAG.sub(replace, source)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned).strip()
    return cleaned, directives


def _normalized_lora_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if name.endswith(".safetensors"):
        name = name[: -len(".safetensors")]
    return name


def _record_match_score(record: dict[str, Any], requested: str) -> int:
    raw = str(requested or "").strip().lower()
    normalized = _normalized_lora_name(requested)
    filename = str(record.get("filename") or "").strip().lower()
    name = str(record.get("name") or "").strip().lower()
    stem = Path(filename).stem.lower()

    if raw and filename == raw:
        return 3
    if normalized and stem == normalized:
        return 2
    if normalized and name == normalized:
        return 1
    return 0


def _matching_records(
    requested: str,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scored = [
        (_record_match_score(record, requested), record)
        for record in records
    ]
    best = max((score for score, _record in scored), default=0)
    if best <= 0:
        return []
    return [record for score, record in scored if score == best]


def lora_catalog(family: str | None = None) -> list[dict[str, Any]]:
    records = list_models(family=family, kind="loras", limit=2000)
    return [
        {
            "id": str(record.get("id") or ""),
            "family": str(record.get("family") or ""),
            "kind": "loras",
            "name": str(record.get("name") or ""),
            "filename": str(record.get("filename") or ""),
            "path": str(record.get("path") or ""),
            "size_bytes": int(record.get("size_bytes") or 0),
            "preview_path": record.get("preview_path"),
        }
        for record in records
    ]


def resolve_lora(
    name: str,
    family: str,
    *,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requested = str(name or "").strip()
    selected_family = str(family or "").strip().lower()
    if not requested:
        raise LoRAError("LoRA name cannot be empty.")
    if not selected_family:
        raise LoRAError("A model family is required to resolve a LoRA.")

    catalog = records if records is not None else lora_catalog()
    compatible = [
        record for record in catalog
        if str(record.get("family") or "").lower() == selected_family
    ]
    matches = _matching_records(requested, compatible)
    if len(matches) > 1:
        paths = ", ".join(str(item.get("path") or "") for item in matches[:4])
        raise LoRAError(
            f"LoRA '{requested}' is ambiguous for {selected_family}: {paths}"
        )
    if len(matches) == 1:
        return deepcopy(matches[0])

    other_matches = _matching_records(
        requested,
        [
            record for record in catalog
            if str(record.get("family") or "").lower() != selected_family
        ],
    )
    if other_matches:
        found = sorted(
            {
                str(record.get("family") or "unknown")
                for record in other_matches
            }
        )
        raise LoRAError(
            f"LoRA '{requested}' was found for {', '.join(found)}, "
            f"but the active model family is {selected_family}."
        )

    raise LoRAError(
        f"LoRA '{requested}' was not found for model family {selected_family}. "
        "Rescan Models after adding it to that family's LoRA directory."
    )


def resolve_lora_directives(
    directives: list[dict[str, Any]],
    family: str,
    *,
    records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    catalog = records if records is not None else lora_catalog()
    resolved_by_id: dict[str, dict[str, Any]] = {}

    for directive in directives:
        record = resolve_lora(
            str(directive.get("name") or ""),
            family,
            records=catalog,
        )
        model_id = str(record["id"])
        resolved_by_id[model_id] = {
            **record,
            "requested_name": str(directive.get("name") or ""),
            "weight": float(directive.get("weight", 1.0)),
            "adapter_name": f"morphorum_{model_id}",
        }

    return list(resolved_by_id.values())


def parse_and_resolve_prompt_loras(
    prompt: Any,
    negative_prompt: Any,
    family: str,
    *,
    records: list[dict[str, Any]] | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    clean_prompt, directives = parse_lora_tags(prompt)
    clean_negative, negative_directives = parse_lora_tags(negative_prompt)
    if negative_directives:
        raise LoRAError(
            "LoRA directives are global adapter controls; place <lora:name:weight> "
            "tags in the positive prompt, not the negative prompt."
        )
    resolved = resolve_lora_directives(
        directives,
        family,
        records=records,
    ) if directives else []
    return clean_prompt, clean_negative, resolved


def resolve_transition_loras(
    transition: dict[str, Any],
    family: str,
    *,
    records: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cleaned = deepcopy(transition)
    from_text, from_directives = parse_lora_tags(cleaned.get("from_text"))
    to_text, to_directives = parse_lora_tags(cleaned.get("to_text"))
    cleaned["from_text"] = from_text
    cleaned["to_text"] = to_text

    from_weights = {
        _normalized_lora_name(item["name"]): item
        for item in from_directives
    }
    to_weights = {
        _normalized_lora_name(item["name"]): item
        for item in to_directives
    }
    names = sorted(set(from_weights) | set(to_weights))
    if not names:
        return cleaned, []

    from_factor = float(cleaned.get("from_weight") or 0.0)
    to_factor = float(cleaned.get("to_weight") or 0.0)
    directives: list[dict[str, Any]] = []
    for normalized in names:
        from_item = from_weights.get(normalized)
        to_item = to_weights.get(normalized)
        display_name = str(
            (to_item or from_item or {}).get("name") or normalized
        )
        weight = (
            float((from_item or {}).get("weight", 0.0)) * from_factor
            + float((to_item or {}).get("weight", 0.0)) * to_factor
        )
        directives.append({"name": display_name, "weight": weight})

    return cleaned, resolve_lora_directives(
        directives,
        family,
        records=records,
    )
