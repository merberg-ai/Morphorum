"""MS6.4 versioned onboarding examples, using native project normalization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .animation_projects import create_animation_project_once, load_animation_project, new_animation_project_template
from .generation import CAPABILITIES
from .model_index import get_model
from .paths import ROOT
from .setup_state import SetupStateError, reserve_setup_example

_MANIFEST = ROOT / "config" / "examples" / "first-run-dolly.json"
_VALID_IDS = ("gentle-dolly-in", "gentle-dolly-out")


def example_catalog() -> dict[str, Any]:
    """Static bundled data, no filesystem traversal or user-supplied path."""
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupStateError("Bundled onboarding examples are unavailable.") from exc
    entries = data.get("examples")
    if (data.get("schema_version") != 1 or not isinstance(entries, list)
            or [x.get("id") for x in entries if isinstance(x, dict)] != list(_VALID_IDS)
            or len(entries) != 2):
        raise SetupStateError("Unexpected onboarding template manifest version.")
    return data


def eligible_model(model_id: str) -> dict[str, Any] | None:
    if not model_id:
        return None
    # Query the managed manager first so it can verify and refresh its index.
    # Never claim that partial weights are a loadable checkpoint.
    if model_id == "managed:zimage-turbo":
        from .managed_models import managed_model_manager
        if not managed_model_manager.status("zimage-turbo")["installed"]:
            raise SetupStateError("Managed Z-Image package has not finished verifying.")
    record = get_model(model_id)
    if not record or record.get("kind") != "checkpoints" or record.get("family") not in CAPABILITIES:
        raise SetupStateError("Selected model is no longer indexed as an eligible checkpoint.")
    return record


def build_example(template_id: str, model_id: str) -> dict[str, Any]:
    manifest = example_catalog()
    match = next((e for e in manifest["examples"] if e["id"] == template_id), None)
    if match is None:
        raise SetupStateError("Unknown onboarding example.")
    model = eligible_model(model_id)
    project = new_animation_project_template()
    project.update({
        "name": match["name"] + " · First Run",
        "notes": (
            "Morphorum first-run example (" + manifest["version"] + "). " +
            match["description"] +
            " Press Preview Camera Motion before rendering. No render has been started. " +
            ("Choose a compatible base model before rendering." if model is None else
             "Review the selected base model before rendering.")
        ),
        "prompts": {"0": manifest["scene_prompt"]},
        "negative_prompts": {"0": ""},
    })
    project["animation"].update(manifest["animation"])
    project["camera_3d"].update({
        "translation_x": "0:(0)",
        "translation_y": "0:(0)",
        "translation_z": f"0:(0), 47:({float(match['camera_z_end']):g})",
        "rotation_x": "0:(0)",
        "rotation_y": "0:(0)",
        "rotation_z": "0:(0)",
        "fov": "0:(40)",
        "projection_mode": "splat",
    })
    project["motion"].update({
        "angle": "0:(0)", "zoom": "0:(1.0)",
        "translation_x": "0:(0)", "translation_y": "0:(0)",
    })
    project["cadence"]["diffusion"] = "0:(2)"
    project["generation"].update({
        "strength": "0:(0.65)",
        "noise": "0:(0.02)",
        "seed": int(manifest["seed"]),
        "seed_behavior": "fixed",
        "seed_increment": 1,
    })
    if model:
        family = str(model["family"])
        variant = str(model.get("variant") or "")
        capability = CAPABILITIES[family]
        overrides = capability.get("variants", {}).get(variant, {})
        project["model"] = {"model_id": model["id"], "family": family, "variant": variant}
        project["generation"]["sampler"] = capability["samplers"]["default"]
        project["generation"]["steps"] = f"0:({int(overrides.get('steps', capability['steps'])['default'])})"
        project["generation"]["guidance"] = (
            f"0:({float(overrides.get('guidance', capability['guidance'])['default']):g})"
        )
    else:
        project["model"] = {"model_id": "", "family": "", "variant": ""}
        project["generation"].update({"sampler": "flowmatch_euler", "steps": "0:(9)", "guidance": "0:(0)"})
    # Never include independently authored tracks: the canonical project
    # normalization derives synchronized timeline keyframes from these fields.
    project.pop("tracks", None)
    return project


def instantiate_example(
    *,
    template_id: str,
    model_id: str,
    revision: int,
    forced: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # Validate inputs and package BEFORE reserving. Saved reservation remains
    # the source of truth if a process dies between reservation and file write.
    payload = build_example(template_id, model_id)
    state = reserve_setup_example(
        template_id=template_id, model_id=model_id, revision=revision, forced=forced,
    )
    project_id = state["example_project_id"]
    project = create_animation_project_once(project_id, payload)
    return project, state


def existing_example(project_id: str | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    try:
        return load_animation_project(project_id)
    except Exception:
        return None
