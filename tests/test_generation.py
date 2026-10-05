from __future__ import annotations

from pathlib import Path

import pytest

import morphorum.generation as generation
from morphorum.generation import GenerationError, GenerationJob, GenerationManager, GenerationRequest


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
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
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
    with pytest.raises(GenerationError, match="Flux is an enabled Morphorum model family"):
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


def test_first_adapter_rejects_indexed_unsupported_checkpoint_extension(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.gguf"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
    manager = GenerationManager()

    with pytest.raises(GenerationError, match="only supports .*\\.ckpt.*\\.safetensors"):
        manager._validate_request(GenerationRequest(model_id="model-1", prompt="test"))


def test_cuda_oom_is_rewritten_as_actionable_error() -> None:
    manager = GenerationManager()
    error = manager._friendly_error(
        RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"),
        action="loading checkpoint 'Test Model'",
    )

    message = str(error)
    assert "GPU memory exhausted" in message
    assert "lower resolution" in message
    assert "clear the CUDA cache" in message


def test_failed_job_unloads_pipeline_and_records_friendly_error(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    request = GenerationRequest(model_id="model-1", prompt="test")
    job = GenerationJob(id="job-1", request=request, model=fake_model(checkpoint))
    manager = GenerationManager()

    cleanup_calls: list[str] = []
    manifest_calls: list[str] = []
    monkeypatch.setattr(manager, "_unload_pipeline", lambda: cleanup_calls.append("cleanup"))
    monkeypatch.setattr(manager, "_write_manifest", lambda failed_job: manifest_calls.append(failed_job.id))

    manager._fail_job(job, RuntimeError("CUDA out of memory while allocating tensor"))

    assert cleanup_calls == ["cleanup"]
    assert manifest_calls == ["job-1"]
    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.eta_seconds is None
    assert job.error is not None
    assert "GPU memory exhausted" in job.error


def test_retired_sd15_family_is_rejected(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "legacy.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sd15"))
    manager = GenerationManager()

    with pytest.raises(GenerationError, match="not supported"):
        manager._validate_request(GenerationRequest(model_id="model-1", prompt="test"))


def test_manual_model_unload_and_busy_guard(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    manager = GenerationManager()
    manager._pipeline = object()
    manager._pipeline_model_id = "model-1"
    manager._pipeline_device = "cuda"

    cleanup_calls: list[str] = []

    def cleanup() -> None:
        cleanup_calls.append("cleanup")
        manager._pipeline = None
        manager._pipeline_model_id = None
        manager._pipeline_device = None

    monkeypatch.setattr(manager, "_unload_pipeline", cleanup)
    result = manager.unload_model()
    assert result["status"] == "unloaded"
    assert result["loaded"] is False
    assert cleanup_calls == ["cleanup"]

    active = GenerationJob(
        id="active-job",
        request=GenerationRequest(model_id="model-1", prompt="test"),
        model=fake_model(checkpoint),
        status="generating",
    )
    manager._jobs[active.id] = active
    manager._pipeline = object()
    with pytest.raises(GenerationError, match="while generation is active"):
        manager.unload_model()


def test_unload_after_generation_setting(monkeypatch) -> None:
    manager = GenerationManager()
    monkeypatch.setattr(
        generation,
        "load_settings",
        lambda: {"performance": {"unload_after_generation": True}},
    )
    assert manager._unload_after_generation_enabled() is True

    monkeypatch.setattr(
        generation,
        "load_settings",
        lambda: {"performance": {"unload_after_generation": False}},
    )
    assert manager._unload_after_generation_enabled() is False
