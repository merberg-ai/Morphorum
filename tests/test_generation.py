from __future__ import annotations

from pathlib import Path

import pytest

import morphorum.generation as generation
from morphorum.generation import GenerationError, GenerationManager, GenerationRequest


def fake_model(path: Path, family: str = "sdxl") -> dict:
    return {
        "id": "model-1",
        "family": family,
        "kind": "checkpoints",
        "name": "Test Model",
        "filename": path.name,
        "path": str(path),
        "extension": path.suffix,
    }


def test_increment_and_fixed_seed_resolution(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint))
    manager = GenerationManager()

    request = GenerationRequest(
        model_id="model-1",
        prompt="test",
        seed=100,
        seed_mode="increment",
        seed_increment=3,
        images=4,
    )
    manager._validate_request(request)
    assert manager._resolve_seeds(request) == [100, 103, 106, 109]

    request.seed_mode = "fixed"
    assert manager._resolve_seeds(request) == [100, 100, 100, 100]


def test_random_seed_resolution_produces_requested_count(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sd15"))
    manager = GenerationManager()
    request = GenerationRequest(model_id="model-1", prompt="test", seed_mode="random", images=5)
    manager._validate_request(request)
    seeds = manager._resolve_seeds(request)
    assert len(seeds) == 5
    assert all(0 <= seed <= 2**32 - 1 for seed in seeds)


def test_unsupported_family_is_rejected(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "flux.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "flux"))
    manager = GenerationManager()
    with pytest.raises(GenerationError, match="Flux model adapter"):
        manager._validate_request(GenerationRequest(model_id="model-1", prompt="test"))


def test_lora_tag_is_recognized_but_rejected_until_loader_lands(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
    manager = GenerationManager()
    with pytest.raises(GenerationError, match="LoRA loading"):
        manager._validate_request(
            GenerationRequest(model_id="model-1", prompt="portrait <lora:detail:0.8>")
        )
