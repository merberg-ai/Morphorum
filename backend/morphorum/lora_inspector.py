from __future__ import annotations

"""Read-only, CPU-light inspection of indexed LoRA files.

Never deserializes pickle checkpoints and never loads tensor data onto a GPU.
"""

import json
import re
from html.parser import HTMLParser
from collections import Counter
from pathlib import Path
from typing import Any

from .model_index import get_model


class LoRAInspectionError(ValueError):
    pass


MAX_SIDECAR_BYTES = 1024 * 1024
MAX_META_VALUE_LENGTH = 1600

TRIGGER_FIELDS = ("trainedWords", "trained_words", "trigger_words", "triggerWords", "activation_text", "ss_trigger_words", "ss_trigger_word")
BASE_FIELDS = ("baseModel", "base_model", "ss_base_model_version", "ss_sd_model_name", "ss_v2")
TRAINING_FIELDS = (
    "ss_network_module", "ss_network_dim", "ss_network_alpha", "ss_learning_rate",
    "ss_num_epochs", "ss_epoch", "ss_steps", "ss_max_train_steps",
    "ss_total_batch_size", "ss_resolution", "ss_optimizer", "ss_optimizer_type",
    "ss_lr_scheduler", "ss_clip_skip", "ss_output_name", "ss_training_started_at",
    "ss_training_finished_at", "ss_dataset_dirs", "ss_sd_scripts_commit_hash",
)


def _words(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(dict.fromkeys(word for item in value for word in _words(item)))[:64]
    if isinstance(value, dict):
        # Sometimes Civitai sidecars include comma-separated or nested trained words.
        return _words(value.get("trainedWords") or value.get("trigger_words"))
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, (list, dict)):
            return _words(parsed)
    except (ValueError, TypeError):
        pass
    return list(dict.fromkeys(part.strip() for part in value.replace("\n", ",").split(",") if part.strip()))[:64]


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _first_value(mapping: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in mapping and mapping[name] not in (None, "", [], {}):
            return mapping[name]
    return None


def _sidecar(path: Path) -> tuple[dict[str, Any], str | None]:
    names = [
        path.with_suffix(".civitai.info"),
        path.with_suffix(".civitai.json"),
        path.with_suffix(".json"),
        path.with_name(path.name + ".json"),
    ]
    for candidate in names:
        try:
            if not candidate.is_file() or candidate.stat().st_size > MAX_SIDECAR_BYTES:
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                return payload, candidate.name
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return {}, None


class _SidecarHTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.words: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and len(" ".join(self.words)) < 3000:
            self.words.append(data)


def _local_html_info(path: Path) -> dict[str, Any] | None:
    for candidate in (path.with_suffix(".html"), path.with_suffix(".civitai.html")):
        try:
            if not candidate.is_file() or candidate.stat().st_size > MAX_SIDECAR_BYTES:
                continue
            raw = candidate.read_text(encoding="utf-8-sig", errors="replace")
            parser = _SidecarHTMLText()
            parser.feed(raw)
            match = re.search(r"https?://(?:www\\.)?civitai\\.com/models/(\\d+)(?:\\?[^\\s\"<>]*)?", raw, re.I)
            return {
                "filename": candidate.name,
                "text_excerpt": " ".join(" ".join(parser.words).split())[:3000],
                "civitai_model_id": int(match.group(1)) if match else None,
            }
        except (OSError, ValueError):
            continue
    return None


def _component(key: str) -> str:
    name = key.lower()
    if name.startswith(("lora_te1_", "lora_te_", "text_encoder.")):
        return "text_encoder"
    if name.startswith(("lora_te2_", "text_encoder_2.")):
        return "text_encoder_2"
    if name.startswith(("lora_unet_", "unet.")):
        return "unet"
    if name.startswith(("lora_transformer_", "transformer.", "diffusion_model.", "diffusion_model_", "lora_diffusion_model_")):
        return "transformer"
    return "unknown"


def _adapter_format(keys: list[str]) -> str:
    if any(key.startswith(("lora_unet_", "lora_te1_", "lora_te2_", "lora_te_")) for key in keys):
        return "kohya/sgm"
    if any(".lora_A." in key or ".lora_B." in key for key in keys):
        return "diffusers/peft"
    if any("lora_down.weight" in key or "lora_up.weight" in key for key in keys):
        return "kohya-like"
    return "unknown"


def _tag_frequencies(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    source = _parse_json(metadata.get("ss_tag_frequency"))
    if not isinstance(source, dict):
        return []
    counts: Counter[str] = Counter()
    for entry in source.values():
        if not isinstance(entry, dict):
            continue
        for label, count in entry.items():
            if not isinstance(label, str):
                continue
            try:
                counts[label] += max(0, int(count))
            except (TypeError, ValueError):
                continue
    return [{"tag": tag, "count": amount} for tag, amount in counts.most_common(24)]


def inspect_lora(model_id: str) -> dict[str, Any]:
    record = get_model(model_id)
    if not record or record.get("kind") != "loras":
        raise LoRAInspectionError("Indexed LoRA not found. Scan Models to refresh the library.")
    path = Path(str(record.get("path") or ""))
    if not path.is_file():
        raise LoRAInspectionError("LoRA file is missing. Scan Models to refresh the library.")

    metadata: dict[str, Any] = {}
    counts: Counter[str] = Counter()
    rank_counts: Counter[int] = Counter()
    tensor_count = 0
    adapter_keys: list[str] = []
    shape_examples: list[dict[str, Any]] = []
    errors: list[str] = []
    file_format = path.suffix.lower().lstrip(".")
    if path.suffix.lower() == ".safetensors":
        try:
            from safetensors import safe_open

            with safe_open(str(path), framework="pt", device="cpu") as handle:
                metadata = dict(handle.metadata() or {})
                keys = list(handle.keys())
                tensor_count = len(keys)
                for key in keys:
                    part = _component(key)
                    counts[part] += 1
                    if len(adapter_keys) < 24:
                        adapter_keys.append(key)
                    if (".lora_A." in key or ".lora_down." in key or key.endswith(".lora_down.weight")):
                        try:
                            shape = list(handle.get_slice(key).get_shape())
                            if len(shape) >= 2:
                                rank_counts[int(shape[0])] += 1
                            if len(shape_examples) < 12:
                                shape_examples.append({"key": key, "shape": shape})
                        except (ValueError, RuntimeError, OSError) as exc:
                            errors.append(f"Could not inspect tensor shape: {type(exc).__name__}")
                adapter_format = _adapter_format(keys)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"Unable to read safetensors header: {type(exc).__name__}: {str(exc)[:180]}")
            adapter_format = "unreadable"
    else:
        # .pt/.ckpt/.pth may be pickle-encoded; never execute their contents to inspect metadata.
        adapter_format = "not-inspected"
        errors.append("Unsafe or unsupported container format: tensor metadata not read (pickle execution is disabled).")

    sidecar, sidecar_name = _sidecar(path)
    embedded_words = _words(_first_value(metadata, TRIGGER_FIELDS))
    nested_version = sidecar.get("modelVersion") if isinstance(sidecar.get("modelVersion"), dict) else {}
    sidecar_words = _words(_first_value(sidecar, TRIGGER_FIELDS) or _first_value(nested_version, TRIGGER_FIELDS))
    triggers = embedded_words or sidecar_words
    trigger_source = ("safetensors metadata" if embedded_words else
                      f"sidecar {sidecar_name}" if sidecar_words else "not recorded")
    base = (_first_value(metadata, BASE_FIELDS) or _first_value(sidecar, BASE_FIELDS)
            or _first_value(nested_version, BASE_FIELDS))
    html_info = _local_html_info(path)
    # A family selected by a user in Settings is an indexing label, not proof of architecture.
    reported_families = {
        "sdxl": ("sdxl", "sd_xl", "illustrious", "pony"),
        "flux": ("flux",),
        "zimage": ("z-image", "z_image", "zimage"),
    }
    base_text = str(base or "").lower()
    hinted = next((fam for fam, matches in reported_families.items()
                   if any(term in base_text for term in matches)), None)
    family = str(record.get("family") or "")
    warnings: list[str] = []
    if hinted and hinted != family:
        warnings.append(f"Metadata suggests {hinted}, but this file is indexed under {family}. Verify its configured directory.")
    if not triggers:
        warnings.append("No explicit trigger words found; frequent training tags below are not verified triggers.")
    if family == "sdxl" and counts["text_encoder"] + counts["text_encoder_2"]:
        warnings.append("This LoRA includes text-encoder weights. Morphorum's B4 SDXL compatibility fallback may skip them.")
    if file_format != "safetensors":
        warnings.append("Use safetensors for safe header-only metadata inspection.")
    rank = [{"rank": key, "modules": value} for key, value in sorted(rank_counts.items())]
    training = {key: str(metadata[key])[:MAX_META_VALUE_LENGTH] for key in TRAINING_FIELDS if key in metadata}
    safe_metadata = {
        str(key)[:100]: str(value)[:MAX_META_VALUE_LENGTH]
        for key, value in sorted(metadata.items()) if key != "ss_tag_frequency"
    }
    return {
        "id": record["id"], "name": record["name"], "family": family,
        "filename": path.name, "path": str(path), "size_bytes": path.stat().st_size,
        "format": file_format, "adapter_format": adapter_format,
        "metadata_base_model": str(base)[:250] if base is not None else None,
        "base_model_hint_family": hinted, "trigger_words": triggers,
        "trigger_source": trigger_source, "training": training,
        "top_training_tags": _tag_frequencies(metadata),
        "tensor_count": tensor_count, "components": dict(counts),
        "ranks": rank, "shape_examples": shape_examples,
        "key_examples": adapter_keys, "sidecar": sidecar_name,
        "html_sidecar": html_info,
        "metadata": safe_metadata, "metadata_count": len(metadata),
        "errors": list(dict.fromkeys(errors))[:8], "warnings": warnings,
        "inspection": "static header inspection only; does not verify active runtime LoRA effect",
    }
