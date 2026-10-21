"""PS5.1: versioned, bounded prompt-authoring profiles and diagnostics.

These are AUTHORING hints, not GPU/renderer capability certifications.
Word counts are never represented as CLIP tokenizer or inference metrics.
"""
from __future__ import annotations

import re
from typing import Any

PROFILE_VERSION = 1
PROFILE_IDS = {"sdxl": "ps5-sdxl-v1", "flux": "ps5-flux-v1", "zimage": "ps5-zimage-v1"}
PROFILE_DESCRIPTIONS = {
    "sdxl": {
        "name": "SDXL · visual clarity",
        "guidance": (
            "Favor concise subject-first visual descriptions, clear composition, "
            "camera perspective, lighting and medium. Keep recurring characters stable. "
            "Avoid redundant keyword piles, unsupported weights and fake CLIP token-limit claims. "
            "Negative text is an optional separate lane, not an instruction to erase existing negatives."
        ),
        "guideline_words": 180,
        "negative_note": "Whether negative conditioning is used depends on the active SDXL pipeline.",
    },
    "flux": {
        "name": "FLUX · natural-language scenes",
        "guidance": (
            "Use coherent natural-language visual descriptions with stable identity, "
            "spatial composition, action and lighting. Do not add SDXL-style keyword spam "
            "or assume CFG/negative prompt behavior. Do not invent LoRA syntax."
        ),
        "guideline_words": 250,
        "negative_note": "FLUX negative conditioning varies with the selected pipeline; do not promise effect.",
    },
    "zimage": {
        "name": "Z-Image · concise visual direction",
        "guidance": (
            "Prefer concrete, compact subject/action/lighting/camera descriptions. "
            "Preserve continuity across frames, avoid excessive repeated adjectives "
            "and do not claim any fixed sampler, CFG, LoRA or negative-conditioning setting."
        ),
        "guideline_words": 200,
        "negative_note": "Managed Z-Image negative conditioning varies by available pipeline.",
    },
}

_LOCK_MAX = 1000
_WORD = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_LORA = re.compile(r"<lora:[^<>]{1,220}>", re.IGNORECASE)


def profile_catalog() -> dict[str, Any]:
    return {
        "schema_version": PROFILE_VERSION,
        "profiles": [
            {"id": PROFILE_IDS[f], "family": f, "name": details["name"],
             "guidance": details["guidance"], "guideline_words": details["guideline_words"],
             "negative_note": details["negative_note"]}
            for f, details in PROFILE_DESCRIPTIONS.items()
        ],
        "warning": "Length guidance is a word-count heuristic, not tokenizer output or renderer validation.",
    }


def validate_options(payload: dict, family: str, mode: str, frames: list[int]) -> dict:
    from .prompt_studio_ollama import OllamaStoryError

    # Existing PS4 API callers keep their historical provenance unless they
    # explicitly select a versioned PS5 family profile.
    desired = payload.get("profile", "ps4-generic-v1")
    if desired not in (PROFILE_IDS[family], "ps4-generic-v1"):
        raise OllamaStoryError("Prompt profile must match the active model family.")
    original = payload.get("continuity", {})
    if not isinstance(original, dict):
        raise OllamaStoryError("Continuity locks must be an object.")
    if set(original) - {"subject", "style"}:
        raise OllamaStoryError("Unknown continuity lock field.")
    locks = {}
    for key in ("subject", "style"):
        text = original.get(key, "")
        if not isinstance(text, str) or len(text) > _LOCK_MAX or any(
                ord(char) < 32 and char not in "\t\n" for char in text):
            raise OllamaStoryError("Continuity locks must contain at most 1,000 characters of text.")
        locks[key] = text.strip()
    target = payload.get("target_frame")
    if target is not None:
        if mode != "refine" or type(target) is not int or target not in frames:
            raise OllamaStoryError("Target frame must be an existing positive prompt keyframe in Refine mode.")
    return {"profile": desired, "continuity": locks, "target_frame": target}


def continuity_prefix(text: str, locks: dict[str, str]) -> str:
    """Add exact immutable user-authored lock fragments at most once."""
    fragments = []
    for key in ("subject", "style"):
        value = locks[key]
        if value and value.casefold() not in text.casefold():
            fragments.append(value)
    return ", ".join(fragments)


def diagnostics(tracks: dict, family: str, focus_frames: list[int] | None = None) -> tuple[list[dict], list[str]]:
    limit = PROFILE_DESCRIPTIONS[family]["guideline_words"]
    entries, warnings = [], []
    focus = set(focus_frames) if focus_frames is not None else None
    for lane in ("positive", "negative"):
        for point in tracks[lane]["keyframes"]:
            if focus is not None and point["frame"] not in focus:
                continue
            text = point["value"]
            words = len(_WORD.findall(_LORA.sub("", text)))
            tags = len(_LORA.findall(text))
            flag = words > limit if lane == "positive" else words > 100
            entries.append({
                "lane": lane, "frame": point["frame"], "words_approx": words,
                "lora_tags": tags, "long_prompt": flag,
            })
            if flag:
                warnings.append(
                    f"{lane} F{point['frame']}: {words} words; consider reviewing length. "
                    "This is a heuristic, not CLIP tokens or a hard truncation claim."
                )
    return entries, warnings
