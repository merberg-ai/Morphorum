from __future__ import annotations

from pathlib import Path

import pytest

from morphorum.loras import (
    LoRAError,
    parse_and_resolve_prompt_loras,
    parse_lora_tags,
    resolve_lora,
    resolve_transition_loras,
)


def records(tmp_path: Path) -> list[dict]:
    sdxl = tmp_path / "sdxl" / "horror.safetensors"
    flux = tmp_path / "flux" / "horror.safetensors"
    detail = tmp_path / "sdxl" / "detail-style.safetensors"
    for path in (sdxl, flux, detail):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
    return [
        {
            "id": "sdxl-horror",
            "family": "sdxl",
            "kind": "loras",
            "name": "horror",
            "filename": sdxl.name,
            "path": str(sdxl),
            "size_bytes": 4,
            "preview_path": None,
        },
        {
            "id": "flux-horror",
            "family": "flux",
            "kind": "loras",
            "name": "horror",
            "filename": flux.name,
            "path": str(flux),
            "size_bytes": 4,
            "preview_path": None,
        },
        {
            "id": "sdxl-detail",
            "family": "sdxl",
            "kind": "loras",
            "name": "detail-style",
            "filename": detail.name,
            "path": str(detail),
            "size_bytes": 4,
            "preview_path": None,
        },
    ]


def test_parse_lora_tags_strips_directives_and_preserves_weights() -> None:
    cleaned, directives = parse_lora_tags(
        "portrait <lora:horror:0.8> in rain <lora:detail-style:-0.25>"
    )
    assert cleaned == "portrait in rain"
    assert directives == [
        {"name": "horror", "weight": 0.8},
        {"name": "detail-style", "weight": -0.25},
    ]


def test_family_aware_resolution_and_mismatch(tmp_path) -> None:
    catalog = records(tmp_path)

    resolved = resolve_lora("horror.safetensors", "sdxl", records=catalog)
    assert resolved["id"] == "sdxl-horror"

    only_flux = [item for item in catalog if item["family"] == "flux"]
    with pytest.raises(LoRAError, match="found for flux.*active model family is sdxl"):
        resolve_lora("horror", "sdxl", records=only_flux)


def test_prompt_parser_rejects_negative_prompt_lora(tmp_path) -> None:
    with pytest.raises(LoRAError, match="positive prompt"):
        parse_and_resolve_prompt_loras(
            "portrait",
            "blurry <lora:horror:0.5>",
            "sdxl",
            records=records(tmp_path),
        )


def test_transition_lora_weight_blends_with_prompt_transition(tmp_path) -> None:
    transition = {
        "from_frame": 0,
        "to_frame": 100,
        "from_text": "forest <lora:horror:0.0>",
        "to_text": "city <lora:horror:1.0>",
        "from_weight": 0.5,
        "to_weight": 0.5,
        "mode": "blend",
    }

    cleaned, loras = resolve_transition_loras(
        transition,
        "sdxl",
        records=records(tmp_path),
    )

    assert cleaned["from_text"] == "forest"
    assert cleaned["to_text"] == "city"
    assert len(loras) == 1
    assert loras[0]["id"] == "sdxl-horror"
    assert loras[0]["weight"] == pytest.approx(0.5)
    assert loras[0]["adapter_name"] == "morphorum_sdxl-horror"
