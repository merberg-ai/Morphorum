from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

import morphorum.generation as generation
import morphorum.loras as loras_module
from morphorum.generation import GenerationError, GenerationJob, GenerationManager, GenerationRequest


def fake_model(path: Path, family: str = "sdxl", variant: str | None = None) -> dict:
    default_variant = "dev" if family == "flux" else ("turbo" if family == "zimage" else family)
    return {
        "id": "model-1",
        "family": family,
        "variant": variant or default_variant,
        "kind": "checkpoints",
        "name": "Test Model",
        "filename": path.name,
        "path": str(path),
        "extension": path.suffix,
        "source": "managed" if family == "zimage" else "external",
    }


def create_zimage_layout(path: Path, *, complete: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "model_index.json").write_text("{}", encoding="utf-8")
    for name in ("scheduler", "text_encoder", "tokenizer", "transformer", "vae"):
        (path / name).mkdir()
    if complete:
        (path / ".morphorum-managed-complete.json").write_text(
            '{"status":"complete"}',
            encoding="utf-8",
        )
    return path


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


def test_incomplete_zimage_managed_package_is_rejected(tmp_path, monkeypatch) -> None:
    package = create_zimage_layout(tmp_path / "Z-Image-Turbo", complete=False)
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(package, "zimage", "turbo"))
    manager = GenerationManager()

    with pytest.raises(GenerationError, match="missing or incomplete"):
        manager._validate_request(
            GenerationRequest(
                model_id="model-1",
                prompt="test",
                steps=9,
                guidance_scale=0.0,
                sampler="flowmatch_euler",
                width=1024,
                height=1024,
            )
        )


def test_lora_tag_is_resolved_and_removed_from_prompt(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    lora = tmp_path / "detail.safetensors"
    lora.write_bytes(b"fake-lora")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
    monkeypatch.setattr(
        loras_module,
        "list_models",
        lambda **_kwargs: [
            {
                "id": "lora-detail",
                "family": "sdxl",
                "kind": "loras",
                "name": "detail",
                "filename": lora.name,
                "path": str(lora),
                "size_bytes": lora.stat().st_size,
                "preview_path": None,
            }
        ],
    )
    manager = GenerationManager()
    request = GenerationRequest(
        model_id="model-1",
        prompt="portrait <lora:detail:0.8>",
    )

    manager._validate_request(request)

    assert request.prompt == "portrait"
    assert request.loras[0]["id"] == "lora-detail"
    assert request.loras[0]["weight"] == pytest.approx(0.8)


def test_first_adapter_rejects_indexed_unsupported_checkpoint_extension(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.gguf"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
    manager = GenerationManager()

    with pytest.raises(GenerationError, match="only supports .*\\.ckpt.*\\.safetensors"):
        manager._validate_request(GenerationRequest(model_id="model-1", prompt="test"))


def test_cuda_pinned_host_oom_reports_memory_lock_failure_separately() -> None:
    manager = GenerationManager()
    error = manager._friendly_error(
        RuntimeError(
            "CUDA error: out of memory; "
            "Returning 2 (CUDA_ERROR_OUT_OF_MEMORY) from cuMemHostAlloc"
        ),
        action="loading Flux model",
    )
    assert "pinned-host-memory allocation" in str(error)
    assert "cuMemHostAlloc" in str(error)
    assert "non-streamed" in str(error)
    assert "ordinary RAM and VRAM" in str(error)


def test_flux_fp8_lora_error_is_rewritten_with_compatibility_guidance() -> None:
    manager = GenerationManager()
    error = manager._friendly_error(
        RuntimeError('"addmm_cuda" not implemented for \'Float8_e4m3fn\''),
    )
    assert "FP8 CUDA matrix multiplication" in str(error)
    assert "BF16" in str(error)
    assert "restart the app and retry" in str(error)


def test_sdxl_vae_tiling_is_opt_in_and_updates_optimization(monkeypatch) -> None:
    manager = GenerationManager()
    called = []
    pipe = SimpleNamespace(
        vae=SimpleNamespace(enable_tiling=lambda: called.append("tiling"))
    )
    monkeypatch.setattr(
        generation,
        "load_settings",
        lambda: {"performance": {"sdxl_vae_tiling": True}},
    )

    assert manager._apply_sdxl_memory_strategy(pipe, "cuda") is True
    assert called == ["tiling"]
    assert manager.pipeline_optimization() == "native-gpu+vae-tiling"


def test_sdxl_vae_tiling_default_does_not_mutate_vae(monkeypatch) -> None:
    manager = GenerationManager()
    called = []
    pipe = SimpleNamespace(
        vae=SimpleNamespace(enable_tiling=lambda: called.append("tiling"))
    )
    monkeypatch.setattr(
        generation,
        "load_settings",
        lambda: {"performance": {"sdxl_vae_tiling": False}},
    )

    assert manager._apply_sdxl_memory_strategy(pipe, "cuda") is False
    assert called == []
    assert manager.pipeline_optimization() is None


def test_sdxl_vae_tiling_missing_api_falls_back_without_enabling(monkeypatch) -> None:
    manager = GenerationManager()
    monkeypatch.setattr(
        generation,
        "load_settings",
        lambda: {"performance": {"sdxl_vae_tiling": True}},
    )
    assert manager._apply_sdxl_memory_strategy(SimpleNamespace(vae=object()), "cuda") is False
    assert manager.pipeline_optimization() is None


def test_cuda_memory_status_reports_allocator_context_without_mutation(monkeypatch) -> None:
    manager = GenerationManager()
    gib = 1024**3

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda *_args: (2 * gib, 16 * gib))
    monkeypatch.setattr(torch.cuda, "memory_allocated", lambda *_args: 10 * gib)
    monkeypatch.setattr(torch.cuda, "memory_reserved", lambda *_args: 12 * gib)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda *_args: 13 * gib)
    monkeypatch.setattr(torch.cuda, "max_memory_reserved", lambda *_args: 14 * gib)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda *_args: "Test GPU")
    monkeypatch.setattr(
        torch.cuda,
        "get_allocator_backend",
        lambda: "native",
        raising=False,
    )
    monkeypatch.setattr(
        torch.cuda,
        "memory_stats",
        lambda *_args: {
            "active_bytes.all.current": 9 * gib,
            "inactive_split_bytes.all.current": gib // 2,
            "num_alloc_retries": 3,
            "num_ooms": 1,
        },
    )

    status = manager.cuda_memory_status()
    assert status is not None
    assert status["allocator_backend"] == "native"
    assert status["device_name"] == "Test GPU"
    assert status["free_gib"] == pytest.approx(2.0)
    assert status["allocated_gib"] == pytest.approx(10.0)
    assert status["active_gib"] == pytest.approx(9.0)
    assert status["inactive_split_gib"] == pytest.approx(0.5)
    assert status["allocation_retries"] == 3
    assert status["oom_count"] == 1


def test_memory_profile_explains_peak_scope(monkeypatch) -> None:
    manager = GenerationManager()
    monkeypatch.setattr(
        manager,
        "cuda_memory_status",
        lambda: {"allocator_backend": "cudaMallocAsync", "allocated_gib": 11.0},
    )
    monkeypatch.setattr(
        manager,
        "model_status",
        lambda: {"loaded": True, "device": "cuda", "optimization": "native-gpu"},
    )

    profile = manager.memory_profile()
    assert profile["cuda_available"] is True
    assert profile["cuda"]["allocator_backend"] == "cudaMallocAsync"
    assert profile["model"]["optimization"] == "native-gpu"
    assert "high-water" in profile["notes"]["peak_scope"]
    assert "Read-only" in profile["notes"]["sampling"]


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


def test_sampler_capability_and_validation(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(generation, "get_model", lambda _: fake_model(checkpoint, "sdxl"))
    manager = GenerationManager()

    sampler_config = manager.capabilities()["sdxl"]["samplers"]
    sampler_ids = [item["id"] for item in sampler_config["options"]]
    assert sampler_config["default"] == "euler"
    assert sampler_ids == [
        "euler",
        "euler_a",
        "dpmpp_2m",
        "dpmpp_2m_sde",
        "ddim",
        "lms",
        "heun",
        "unipc",
    ]

    request = GenerationRequest(model_id="model-1", prompt="test", sampler="dpmpp_2m")
    manager._validate_request(request)

    with pytest.raises(GenerationError, match="Sampler 'made_up' is not supported"):
        manager._validate_request(
            GenerationRequest(model_id="model-1", prompt="test", sampler="made_up")
        )


def test_all_advertised_sdxl_samplers_construct_from_base_config() -> None:
    from diffusers import EulerDiscreteScheduler

    class FakePipe:
        def __init__(self) -> None:
            self.scheduler = EulerDiscreteScheduler()

    manager = GenerationManager()
    pipe = FakePipe()
    manager._pipeline_scheduler_config = dict(pipe.scheduler.config)

    for sampler in [
        item["id"]
        for item in manager.capabilities()["sdxl"]["samplers"]["options"]
    ]:
        manager._configure_sampler(pipe, "sdxl", sampler)
        assert manager._pipeline_sampler == sampler
        assert pipe.scheduler is not None


def test_flux_dev_and_schnell_capabilities_and_validation(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "flux1-dev.safetensors"
    checkpoint.write_bytes(b"fake")
    manager = GenerationManager()

    dev_model = fake_model(checkpoint, "flux", "dev")
    monkeypatch.setattr(generation, "get_model", lambda _: dev_model)
    dev = manager._effective_capability(dev_model)
    assert dev["supported"] is True
    assert dev["steps"]["default"] == 28
    assert dev["guidance"]["default"] == 1.0
    assert dev["guidance"]["label"] == "CFG"
    assert dev["default_resolution"] == {"width": 1024, "height": 1024}
    assert dev["max_sequence_length"] == 512
    assert dev["samplers"]["default"] == "flowmatch_euler"

    manager._validate_request(
        GenerationRequest(
            model_id="model-1",
            prompt="test",
            steps=28,
            guidance_scale=3.5,
            sampler="flowmatch_euler",
            width=1024,
            height=1024,
        )
    )

    schnell_model = fake_model(checkpoint, "flux", "schnell")
    monkeypatch.setattr(generation, "get_model", lambda _: schnell_model)
    schnell = manager._effective_capability(schnell_model)
    assert schnell["steps"]["default"] == 4
    assert schnell["guidance"]["default"] == 0.0
    assert schnell["default_resolution"] == {"width": 1024, "height": 1024}
    assert schnell["max_sequence_length"] == 256

    manager._validate_request(
        GenerationRequest(
            model_id="model-1",
            prompt="test",
            steps=4,
            guidance_scale=0.0,
            sampler="flowmatch_euler",
            width=1024,
            height=1024,
        )
    )
    with pytest.raises(GenerationError, match="Flux Schnell requires Guidance = 0"):
        manager._validate_request(
            GenerationRequest(
                model_id="model-1",
                prompt="test",
                steps=4,
                guidance_scale=3.5,
                sampler="flowmatch_euler",
            )
        )


def test_flux_requires_safetensors_and_16_pixel_dimensions(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "flux1-dev.ckpt"
    checkpoint.write_bytes(b"fake")
    monkeypatch.setattr(
        generation,
        "get_model",
        lambda _: fake_model(checkpoint, "flux", "dev"),
    )
    manager = GenerationManager()
    request = GenerationRequest(
        model_id="model-1",
        prompt="test",
        sampler="flowmatch_euler",
        steps=28,
        guidance_scale=3.5,
    )
    with pytest.raises(GenerationError, match="only supports .*safetensors"):
        manager._validate_request(request)

    safetensors = tmp_path / "flux1-dev.safetensors"
    safetensors.write_bytes(b"fake")
    monkeypatch.setattr(
        generation,
        "get_model",
        lambda _: fake_model(safetensors, "flux", "dev"),
    )
    request.width = 1032
    request.height = 1024
    with pytest.raises(GenerationError, match="divisible by 16"):
        manager._validate_request(request)


def test_flux_call_arguments_are_variant_specific(tmp_path) -> None:
    checkpoint = tmp_path / "flux.safetensors"
    checkpoint.write_bytes(b"fake")
    manager = GenerationManager()
    generator = object()
    callback = object()

    dev_job = GenerationJob(
        id="dev",
        request=GenerationRequest(
            model_id="model-1",
            prompt="flux prompt",
            negative_prompt="ignored for initial Flux adapter",
            steps=28,
            guidance_scale=3.5,
            sampler="flowmatch_euler",
        ),
        model=fake_model(checkpoint, "flux", "dev"),
    )
    dev_args = manager._build_call_args(dev_job, generator, callback)
    assert dev_args["guidance_scale"] == 3.5
    assert dev_args["max_sequence_length"] == 512
    assert "negative_prompt" not in dev_args

    schnell_job = GenerationJob(
        id="schnell",
        request=GenerationRequest(
            model_id="model-1",
            prompt="flux prompt",
            steps=4,
            guidance_scale=0.0,
            sampler="flowmatch_euler",
        ),
        model=fake_model(checkpoint, "flux", "schnell"),
    )
    schnell_args = manager._build_call_args(schnell_job, generator, callback)
    assert schnell_args["guidance_scale"] == 0.0
    assert schnell_args["max_sequence_length"] == 256


def test_flux_flowmatch_sampler_constructs() -> None:
    from diffusers import FlowMatchEulerDiscreteScheduler

    class FakePipe:
        def __init__(self) -> None:
            self.scheduler = FlowMatchEulerDiscreteScheduler()

    manager = GenerationManager()
    pipe = FakePipe()
    manager._pipeline_scheduler_config = dict(pipe.scheduler.config)
    manager._configure_sampler(pipe, "flux", "flowmatch_euler")
    assert manager._pipeline_sampler == "flowmatch_euler"
    assert isinstance(pipe.scheduler, FlowMatchEulerDiscreteScheduler)


def test_flux_runtime_exposes_required_loader_methods() -> None:
    from diffusers import FluxPipeline, FluxTransformer2DModel
    from diffusers.hooks import apply_group_offloading

    assert callable(getattr(FluxTransformer2DModel, "from_single_file", None))
    assert callable(getattr(FluxPipeline, "from_pretrained", None))
    assert callable(apply_group_offloading)


def test_flux_runtime_exposes_native_fp8_layerwise_casting() -> None:
    import torch
    from diffusers import FluxTransformer2DModel

    assert hasattr(torch, "float8_e4m3fn")
    assert callable(getattr(FluxTransformer2DModel, "enable_layerwise_casting", None))


def test_generation_job_public_includes_performance_metrics(tmp_path) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    job = GenerationJob(
        id="job-perf",
        request=GenerationRequest(model_id="model-1", prompt="test"),
        model=fake_model(checkpoint),
        model_load_seconds=12.5,
        last_step_seconds=3.2,
        average_step_seconds=3.8,
    )
    payload = job.public()
    assert payload["model_load_seconds"] == 12.5
    assert payload["last_step_seconds"] == 3.2
    assert payload["average_step_seconds"] == 3.8
    assert "_started_monotonic" not in payload
    assert "_last_step_monotonic" not in payload
    assert "_step_durations" not in payload


def test_sdxl_capability_has_explicit_ui_defaults() -> None:
    manager = GenerationManager()
    sdxl = manager.capabilities()["sdxl"]
    assert sdxl["default_resolution"] == {"width": 1024, "height": 1024}
    assert sdxl["steps"]["default"] == 25
    assert sdxl["guidance"]["default"] == 6.0
    assert sdxl["samplers"]["default"] == "euler"


def test_zimage_turbo_capabilities_and_validation(tmp_path, monkeypatch) -> None:
    package = create_zimage_layout(tmp_path / "Z-Image-Turbo")
    model = fake_model(package, "zimage", "turbo")
    monkeypatch.setattr(generation, "get_model", lambda _: model)
    manager = GenerationManager()

    capability = manager._effective_capability(model)
    assert capability["supported"] is True
    assert capability["label"] == "Z-Image Turbo"
    assert capability["steps"]["default"] == 9
    assert capability["guidance"]["default"] == 0.0
    assert capability["guidance"]["min"] == 0.0
    assert capability["guidance"]["max"] == 0.0
    assert capability["negative_prompt"] is False
    assert capability["default_resolution"] == {"width": 1024, "height": 1024}
    assert capability["samplers"]["default"] == "flowmatch_euler"
    assert capability["resolutions"][0] == {"label": "Square 1:1", "width": 1024, "height": 1024}

    manager._validate_request(
        GenerationRequest(
            model_id="model-1",
            prompt="a cinematic portrait",
            steps=9,
            guidance_scale=0.0,
            sampler="flowmatch_euler",
            width=1024,
            height=1024,
        )
    )

    with pytest.raises(GenerationError, match="Z-Image Turbo requires Guidance = 0"):
        manager._validate_request(
            GenerationRequest(
                model_id="model-1",
                prompt="test",
                steps=9,
                guidance_scale=1.0,
                sampler="flowmatch_euler",
                width=1024,
                height=1024,
            )
        )


def test_zimage_requires_managed_source(tmp_path, monkeypatch) -> None:
    package = create_zimage_layout(tmp_path / "Z-Image-Turbo")
    model = fake_model(package, "zimage", "turbo")
    model["source"] = "external"
    monkeypatch.setattr(generation, "get_model", lambda _: model)

    with pytest.raises(GenerationError, match="missing or incomplete"):
        GenerationManager()._validate_request(
            GenerationRequest(
                model_id="model-1",
                prompt="test",
                steps=9,
                guidance_scale=0.0,
                sampler="flowmatch_euler",
                width=1024,
                height=1024,
            )
        )


def test_zimage_requires_16_pixel_dimensions(tmp_path, monkeypatch) -> None:
    package = create_zimage_layout(tmp_path / "Z-Image-Turbo")
    monkeypatch.setattr(
        generation,
        "get_model",
        lambda _: fake_model(package, "zimage", "turbo"),
    )
    request = GenerationRequest(
        model_id="model-1",
        prompt="test",
        sampler="flowmatch_euler",
        steps=9,
        guidance_scale=0.0,
        width=1032,
        height=1024,
    )
    with pytest.raises(GenerationError, match="divisible by 16"):
        GenerationManager()._validate_request(request)


def test_zimage_call_arguments_use_turbo_contract(tmp_path) -> None:
    package = create_zimage_layout(tmp_path / "Z-Image-Turbo")
    manager = GenerationManager()
    generator = object()
    callback = object()
    job = GenerationJob(
        id="zimage",
        request=GenerationRequest(
            model_id="model-1",
            prompt="z-image prompt",
            negative_prompt="ignored",
            steps=9,
            guidance_scale=0.0,
            sampler="flowmatch_euler",
            width=1024,
            height=1024,
        ),
        model=fake_model(package, "zimage", "turbo"),
    )

    args = manager._build_call_args(job, generator, callback)
    assert args["prompt"] == "z-image prompt"
    assert args["num_inference_steps"] == 9
    assert args["guidance_scale"] == 0.0
    assert args["width"] == 1024
    assert args["height"] == 1024
    assert args["generator"] is generator
    assert args["callback_on_step_end"] is callback
    assert "negative_prompt" not in args
    assert "max_sequence_length" not in args


def test_zimage_flowmatch_sampler_constructs() -> None:
    from diffusers import FlowMatchEulerDiscreteScheduler

    class FakePipe:
        def __init__(self) -> None:
            self.scheduler = FlowMatchEulerDiscreteScheduler()

    manager = GenerationManager()
    pipe = FakePipe()
    manager._pipeline_scheduler_config = dict(pipe.scheduler.config)
    manager._configure_sampler(pipe, "zimage", "flowmatch_euler")
    assert manager._pipeline_sampler == "flowmatch_euler"
    assert isinstance(pipe.scheduler, FlowMatchEulerDiscreteScheduler)


def test_zimage_runtime_exposes_required_pipeline_api() -> None:
    import inspect

    from diffusers import ZImagePipeline

    assert callable(getattr(ZImagePipeline, "from_pretrained", None))
    assert callable(getattr(ZImagePipeline, "enable_model_cpu_offload", None))
    parameters = inspect.signature(ZImagePipeline.__call__).parameters
    for name in (
        "prompt",
        "height",
        "width",
        "num_inference_steps",
        "guidance_scale",
        "generator",
        "callback_on_step_end",
    ):
        assert name in parameters


def test_model_load_progress_callback_is_clamped() -> None:
    manager = GenerationManager()
    events = []

    manager._notify_load_progress(
        lambda progress, phase, message, detail: events.append(
            (progress, phase, message, detail)
        ),
        1.5,
        "ready",
        "done",
        "detail",
    )

    assert events == [(1.0, "ready", "done", "detail")]



class FakeLoRAPipe:
    def __init__(self) -> None:
        self.loads: list[dict] = []
        self.adapter_calls: list[tuple[list[str], list[float]]] = []
        self.disabled = 0
        self.enabled = 0

    def load_lora_weights(self, path, **kwargs):
        self.loads.append({"path": path, **kwargs})

    def set_adapters(self, names, adapter_weights=None):
        self.adapter_calls.append((list(names), list(adapter_weights or [])))

    def disable_lora(self):
        self.disabled += 1

    def enable_lora(self):
        self.enabled += 1


def test_lora_adapter_loads_once_reweights_and_disables(tmp_path) -> None:
    path = tmp_path / "horror.safetensors"
    path.write_bytes(b"fake-lora")
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    manager = GenerationManager()
    pipe = FakeLoRAPipe()
    base = {
        "id": "horror-id",
        "family": "sdxl",
        "name": "horror",
        "path": str(path),
        "adapter_name": "morphorum_horror-id",
    }

    manager.configure_loras(pipe, model, [{**base, "weight": 0.25}])
    manager.configure_loras(pipe, model, [{**base, "weight": 0.75}])
    manager.configure_loras(pipe, model, [])

    assert len(pipe.loads) == 1
    assert pipe.loads[0]["weight_name"] == path.name
    assert pipe.loads[0]["adapter_name"] == "morphorum_horror-id"
    assert pipe.adapter_calls == [
        (["morphorum_horror-id"], [0.25]),
        (["morphorum_horror-id"], [0.75]),
    ]
    assert pipe.disabled == 1
    assert manager._active_lora_signature == ()


def test_b55_multiple_prompt_windows_reuse_loaded_lora_adapters_without_reload(
    tmp_path: Path,
) -> None:
    manager = GenerationManager()
    pipe = FakeLoRAPipe()
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    adapters = []
    for label in ("forest", "monster", "fog"):
        path = tmp_path / f"{label}.safetensors"
        path.write_bytes(b"fake")
        adapters.append({
            "id": label, "family": "sdxl", "name": label, "path": str(path),
            "adapter_name": f"morphorum_{label}",
        })

    # Simulates three prompt windows and the repeated use of a previously
    # loaded adapter. Only the weights should change after first injection.
    windows = [
        [(adapters[0], 0.3)],
        [(adapters[0], 0.7), (adapters[1], 0.4)],
        [(adapters[1], 0.9), (adapters[2], 0.6)],
        [(adapters[0], 0.5), (adapters[2], 1.0)],
    ]
    for items in windows:
        manager.configure_loras(
            pipe, model, [{**adapter, "weight": weight} for adapter, weight in items],
        )
    assert len(pipe.loads) == 3, "Only the three distinct adapters should load"
    assert len(manager._pipeline_loras) == 3, "Resident LoRA registry is bounded by unique adapters"
    assert len(pipe.adapter_calls) == 4
    assert manager._active_lora_signature == (
        ("morphorum_forest", 0.5), ("morphorum_fog", 1.0),
    )
    manager.configure_loras(pipe, model, [])
    assert manager._active_lora_signature == ()
    assert pipe.disabled == 1


def test_lora_adapter_rejects_family_mismatch(tmp_path) -> None:
    path = tmp_path / "flux-style.safetensors"
    path.write_bytes(b"fake-lora")
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    manager = GenerationManager()

    with pytest.raises(GenerationError, match="active model family is sdxl"):
        manager.configure_loras(
            FakeLoRAPipe(),
            model,
            [{
                "id": "flux-lora",
                "family": "flux",
                "name": "flux-style",
                "path": str(path),
                "adapter_name": "morphorum_flux-lora",
                "weight": 1.0,
            }],
        )



def test_supported_pipeline_families_expose_lora_adapter_api() -> None:
    from diffusers import FluxPipeline, StableDiffusionXLPipeline, ZImagePipeline

    for pipeline_class in (
        StableDiffusionXLPipeline,
        FluxPipeline,
        ZImagePipeline,
    ):
        assert callable(getattr(pipeline_class, "load_lora_weights", None))
        assert callable(getattr(pipeline_class, "set_adapters", None))
        assert callable(getattr(pipeline_class, "disable_lora", None))
        assert callable(getattr(pipeline_class, "enable_lora", None))



class FakeRankBugUNet:
    def __init__(self) -> None:
        self.peft_config = {}
        self.deleted = []
        self.config = SimpleNamespace(layers_per_block=2)

    def delete_adapters(self, adapter_name):
        self.deleted.append(adapter_name)
        self.peft_config.pop(adapter_name, None)


class FakeSDXLRankBugPipe(FakeLoRAPipe):
    def __init__(self, *, partial_unet: bool = False) -> None:
        super().__init__()
        self.partial_unet = partial_unet
        self.unet = FakeRankBugUNet()
        self.unet_loads = []
        self.state_dict_calls = []

    def load_lora_weights(self, source, **kwargs):
        self.loads.append({"path": source, **kwargs})
        adapter_name = kwargs.get("adapter_name")
        if self.partial_unet and adapter_name:
            self.unet.peft_config[adapter_name] = object()
        raise IndexError("list index out of range")

    def lora_state_dict(self, *_args, **kwargs):
        self.state_dict_calls.append(kwargs)
        # Real SDXL conversion requires the model's UNet config to map SGM blocks.
        assert kwargs["unet_config"] is self.unet.config
        assert kwargs["return_lora_metadata"] is True
        assert kwargs["local_files_only"] is True
        return (
            {
                "unet.down_blocks.0.attentions.0.to_q.lora_A.weight": torch.ones(2, 2),
                "unet.down_blocks.0.attentions.0.to_q.lora_B.weight": torch.ones(2, 2),
                "text_encoder.text_model.encoder.layers.0.self_attn.q_proj.lora_A.weight": torch.ones(2, 2),
            },
            {
                "unet.down_blocks.0.attentions.0.to_q.alpha": 2.0,
                "text_encoder.text_model.encoder.layers.0.self_attn.q_proj.alpha": 2.0,
            },
        )

    def load_lora_into_unet(self, **kwargs):
        self.unet_loads.append(kwargs)
        adapter_name = kwargs["adapter_name"]
        self.unet.peft_config[adapter_name] = object()


def _write_mixed_sdxl_lora(path: Path) -> None:
    import torch
    from safetensors.torch import save_file

    save_file(
        {
            "lora_unet_down_blocks_0_attentions_0_to_q.lora_down.weight": torch.ones(2, 2),
            "lora_unet_down_blocks_0_attentions_0_to_q.lora_up.weight": torch.ones(2, 2),
            "lora_unet_down_blocks_0_attentions_0_to_q.alpha": torch.tensor(2.0),
            "lora_te1_text_model_encoder_layers_0_self_attn_q_proj.lora_down.weight": torch.ones(2, 2),
            "lora_te1_text_model_encoder_layers_0_self_attn_q_proj.lora_up.weight": torch.ones(2, 2),
            "lora_te2_text_model_encoder_layers_0_self_attn_q_proj.lora_down.weight": torch.ones(2, 2),
        },
        str(path),
    )


def test_sdxl_rank_bug_retries_with_unet_only_state_dict(tmp_path) -> None:
    path = tmp_path / "mixed-sdxl.safetensors"
    _write_mixed_sdxl_lora(path)
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    manager = GenerationManager()
    pipe = FakeSDXLRankBugPipe()
    item = {
        "id": "mixed-id",
        "family": "sdxl",
        "name": "mixed-sdxl",
        "path": str(path),
        "adapter_name": "morphorum_mixed-id",
        "weight": 0.8,
    }

    loaded = manager.configure_loras(pipe, model, [item])

    assert loaded == [item]
    assert len(pipe.loads) == 1
    assert pipe.loads[0]["weight_name"] == path.name
    assert len(pipe.unet_loads) == 1
    assert len(pipe.state_dict_calls) == 1
    fallback = pipe.unet_loads[0]
    assert fallback["adapter_name"] == "morphorum_mixed-id"
    assert fallback["state_dict"]
    assert all(
        not key.startswith(("text_encoder.", "text_encoder_2."))
        for key in fallback["state_dict"]
    )
    assert any(key.startswith("unet.") for key in fallback["state_dict"])
    assert manager._pipeline_loras["mixed-id"]["compatibility"] == "sdxl-clean-unet-only"
    assert pipe.adapter_calls == [(["morphorum_mixed-id"], [0.8])]


class FakeVerifiedSDXLComponent:
    """Small PEFT observable stand-in with a selectable CLIP module namespace."""

    def __init__(self, target: str):
        self.target = target
        self.config = SimpleNamespace(layers_per_block=2)
        self.peft_config = {}
        self.lora_A = {}

    def named_modules(self):
        yield "", self
        yield self.target, self
        if ".q_proj" in self.target:
            yield self.target.replace(".q_proj", ".out_proj"), self

    def named_parameters(self):
        for adapter in self.peft_config:
            yield f"{self.target}.lora_A.{adapter}.weight", torch.ones(2, 2)
            yield f"{self.target}.lora_B.{adapter}.weight", torch.ones(2, 2)

    def inject(self, adapter: str):
        self.peft_config[adapter] = object()
        self.lora_A[adapter] = object()

    def delete_adapters(self, adapter: str):
        self.peft_config.pop(adapter, None)
        self.lora_A.pop(adapter, None)


class FakeSDXLFullRankRepairPipe(FakeSDXLRankBugPipe):
    """The real Diffusers loader fails; the component loader verifies the fix."""

    def __init__(self, *, second_encoder_has_wrapper=False, key_style="peft"):
        super().__init__(partial_unet=True)
        self.key_style = key_style
        self.unet = FakeVerifiedSDXLComponent("down_blocks.0.attentions.0.to_q")
        self.text_encoder = FakeVerifiedSDXLComponent(
            "encoder.layers.0.self_attn.q_proj"
        )
        second_name = "encoder.layers.0.self_attn.q_proj"
        if second_encoder_has_wrapper:
            second_name = "text_model." + second_name
        self.text_encoder_2 = FakeVerifiedSDXLComponent(second_name)
        self.encoder_loads = []

    def load_lora_weights(self, source, **kwargs):
        self.loads.append({"path": source, **kwargs})
        self.unet.inject(str(kwargs["adapter_name"]))
        raise IndexError("list index out of range")

    def lora_state_dict(self, *_args, **kwargs):
        assert kwargs["unet_config"] is self.unet.config
        target = "text_model.encoder.layers.0.self_attn.q_proj"
        if self.key_style == "kohya":
            target = target.replace(".q_proj", ".to_q_lora")
            down, up = ".down.weight", ".up.weight"
        else:
            down, up = ".lora_A.weight", ".lora_B.weight"
        weights = {
            "unet.down_blocks.0.attentions.0.to_q.lora_A.weight": torch.ones(2, 2),
            "unet.down_blocks.0.attentions.0.to_q.lora_B.weight": torch.ones(2, 2),
            f"text_encoder.{target}{down}": torch.ones(2, 2),
            f"text_encoder.{target}{up}": torch.ones(2, 2),
            f"text_encoder_2.{target}{down}": torch.ones(2, 2),
            f"text_encoder_2.{target}{up}": torch.ones(2, 2),
        }
        if self.key_style == "kohya":
            # Diffusers' old-format detector keys off to_out_lora.
            out_target = target.replace("to_q_lora", "to_out_lora")
            for name in ("text_encoder", "text_encoder_2"):
                weights[f"{name}.{out_target}.down.weight"] = torch.ones(2, 2)
                weights[f"{name}.{out_target}.up.weight"] = torch.ones(2, 2)
        return (
            weights,
            {
                f"text_encoder.{target}.alpha": 2.0,
                f"text_encoder_2.{target}.alpha": 4.0,
            },
            None,
        )

    def load_lora_into_unet(self, **kwargs):
        self.unet_loads.append(kwargs)
        self.unet.inject(kwargs["adapter_name"])

    def load_lora_into_text_encoder(self, state_dict, **kwargs):
        encoder = kwargs["text_encoder"]
        prefix = kwargs["prefix"]
        module = encoder.target
        if self.key_style == "kohya":
            module = module.replace(".q_proj", ".to_q_lora")
            down, up = ".down.weight", ".up.weight"
        else:
            down, up = ".lora_A.weight", ".lora_B.weight"
        assert f"{prefix}.{module}{down}" in state_dict
        assert f"{prefix}.{module}{up}" in state_dict
        assert f"{prefix}.{module}.alpha" in kwargs["network_alphas"]
        encoder.inject(kwargs["adapter_name"])
        self.encoder_loads.append(prefix)

    def get_list_adapters(self):
        return {
            name: list(getattr(self, name).peft_config)
            for name in ("unet", "text_encoder", "text_encoder_2")
        }


@pytest.mark.parametrize("second_encoder_has_wrapper", [False, True])
@pytest.mark.parametrize("key_style", ["peft", "kohya"])
def test_sdxl_rank_bug_restores_both_text_encoders_and_alphas(
    tmp_path, second_encoder_has_wrapper, key_style,
) -> None:
    path = tmp_path / "mixed-sdxl.safetensors"
    _write_mixed_sdxl_lora(path)
    manager = GenerationManager()
    pipe = FakeSDXLFullRankRepairPipe(
        second_encoder_has_wrapper=second_encoder_has_wrapper,
        key_style=key_style,
    )
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    item = {
        "id": "fixed-id",
        "family": "sdxl",
        "name": "mixed",
        "path": str(path),
        "adapter_name": "morphorum_fixed-id",
        "weight": 0.4,
    }
    manager.configure_loras(pipe, model, [item])

    assert pipe.encoder_loads == ["text_encoder", "text_encoder_2"]
    assert pipe.unet_loads, "UNet weights must remain present"
    assert "morphorum_fixed-id" in pipe.unet.peft_config
    assert "morphorum_fixed-id" in pipe.text_encoder.peft_config
    assert "morphorum_fixed-id" in pipe.text_encoder_2.peft_config
    assert manager._pipeline_loras["fixed-id"]["compatibility"] == (
        "sdxl-text-encoder-normalized"
    )
    verified = manager._pipeline_loras["fixed-id"]["diagnostics"]
    assert set(verified["components"]) == {
        "unet", "text_encoder", "text_encoder_2"
    }
    assert verified["normalized_text_encoder_tensors"] == (8 if key_style == "kohya" else 4)
    assert pipe.adapter_calls == [(["morphorum_fixed-id"], [0.4])]
    # Weight scheduling reuses one registered adapter, with no new load.
    manager.configure_loras(pipe, model, [{**item, "weight": 0.85}])
    assert len(pipe.loads) == 1
    assert len(pipe.encoder_loads) == 2
    assert pipe.adapter_calls[-1] == (["morphorum_fixed-id"], [0.85])


def test_sdxl_namespace_normalizer_rejects_unsupported_clip_modules() -> None:
    pipe = FakeSDXLFullRankRepairPipe()
    state = {
        "text_encoder.text_model.unknown.layers.0.q_proj.lora_B.weight":
            torch.ones(2, 2),
    }
    with pytest.raises(GenerationError, match="no complete CLIP LoRA rank match"):
        GenerationManager._normalize_sdxl_text_encoder_keys(
            pipe, state, {}, None
        )


def test_sdxl_sgm_block_indices_remap_with_unet_config(tmp_path) -> None:
    """Regression for real Kohya keys that became missing 7.1 UNet targets in B4."""
    from diffusers import StableDiffusionXLPipeline
    from safetensors.torch import save_file

    path = tmp_path / "sgm-sdxl.safetensors"
    sgm_key = "lora_unet_input_blocks_7_1_transformer_blocks_3_attn1_to_q"
    save_file(
        {
            f"{sgm_key}.lora_down.weight": torch.ones(2, 2),
            f"{sgm_key}.lora_up.weight": torch.ones(2, 2),
            f"{sgm_key}.alpha": torch.tensor(2.0),
        },
        str(path),
    )
    # Mirrors the UNet config passed by SDXL's own load_lora_weights method.
    state_dict, _alphas = StableDiffusionXLPipeline.lora_state_dict(
        str(path.parent),
        weight_name=path.name,
        local_files_only=True,
        unet_config=SimpleNamespace(layers_per_block=2),
    )
    assert state_dict
    assert all(key.startswith("unet.down_blocks.2.attentions.0.") for key in state_dict)
    assert all("down_blocks.7.1." not in key for key in state_dict)


def test_sdxl_rank_bug_accepts_already_loaded_unet_adapter(tmp_path) -> None:
    path = tmp_path / "partial-sdxl.safetensors"
    _write_mixed_sdxl_lora(path)
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    manager = GenerationManager()
    pipe = FakeSDXLRankBugPipe(partial_unet=True)
    item = {
        "id": "partial-id",
        "family": "sdxl",
        "name": "partial-sdxl",
        "path": str(path),
        "adapter_name": "morphorum_partial-id",
        "weight": 1.0,
    }

    manager.configure_loras(pipe, model, [item])

    assert len(pipe.loads) == 1
    assert len(pipe.unet_loads) == 1
    assert "morphorum_partial-id" in pipe.unet.deleted
    assert "morphorum_partial-id" in pipe.unet.peft_config
    assert manager._pipeline_loras["partial-id"]["compatibility"] == "sdxl-clean-unet-only"
    assert pipe.adapter_calls == [(["morphorum_partial-id"], [1.0])]


def test_rank_bug_fallback_is_not_used_for_non_sdxl(tmp_path) -> None:
    path = tmp_path / "flux.safetensors"
    _write_mixed_sdxl_lora(path)
    model = fake_model(tmp_path / "model.safetensors", "flux")
    manager = GenerationManager()
    pipe = FakeSDXLRankBugPipe()
    item = {
        "id": "flux-id",
        "family": "flux",
        "name": "flux-lora",
        "path": str(path),
        "adapter_name": "morphorum_flux-id",
        "weight": 1.0,
    }

    with pytest.raises(GenerationError, match="IndexError: list index out of range"):
        manager.configure_loras(pipe, model, [item])

    assert len(pipe.loads) == 1



class FakeTrackedLoRAPipe(FakeLoRAPipe):
    def __init__(self, adapters=()) -> None:
        super().__init__()
        self.adapters = set(adapters)
        self.active_adapters: list[str] = []

    def load_lora_weights(self, path, **kwargs):
        super().load_lora_weights(path, **kwargs)
        adapter_name = kwargs.get("adapter_name")
        if adapter_name:
            self.adapters.add(str(adapter_name))

    def set_adapters(self, names, adapter_weights=None):
        super().set_adapters(names, adapter_weights)
        self.active_adapters = [str(name) for name in names]

    def get_list_adapters(self):
        return {"unet": sorted(self.adapters)}

    def get_active_adapters(self):
        return list(self.active_adapters)


def test_task_switch_reasserts_existing_lora_even_when_weight_is_unchanged(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "style.safetensors"
    path.write_bytes(b"fake-lora")
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    adapter_name = "morphorum-style-id"
    source = FakeTrackedLoRAPipe([adapter_name])
    converted = FakeTrackedLoRAPipe([adapter_name])
    manager = GenerationManager()
    manager._pipeline = source
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._pipeline_loras = {
        "style-id": {
            "id": "style-id",
            "name": "style",
            "family": "sdxl",
            "path": str(path),
            "adapter_name": adapter_name,
            "compatibility": None,
        }
    }
    manager._active_lora_signature = ((adapter_name, 0.8),)
    manager._verified_lora_adapters = (adapter_name,)

    monkeypatch.setattr(
        manager,
        "_convert_pipeline_task",
        lambda _pipe, _family, _task: converted,
    )
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_kwargs: None)

    switched = manager._switch_loaded_pipeline_task(model, "img2img")

    assert switched is converted
    assert manager._active_lora_signature == ()
    assert manager._verified_lora_adapters == ()

    item = {
        "id": "style-id",
        "family": "sdxl",
        "name": "style",
        "path": str(path),
        "adapter_name": adapter_name,
        "weight": 0.8,
    }
    manager.configure_loras(switched, model, [item])

    assert converted.loads == []
    assert converted.adapter_calls == [([adapter_name], [0.8])]
    assert converted.get_active_adapters() == [adapter_name]
    assert manager._verified_lora_adapters == (adapter_name,)


def test_task_switch_reloads_cached_lora_missing_from_converted_pipeline(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "style.safetensors"
    path.write_bytes(b"fake-lora")
    model = fake_model(tmp_path / "model.safetensors", "sdxl")
    adapter_name = "morphorum-style-id"
    source = FakeTrackedLoRAPipe([adapter_name])
    converted = FakeTrackedLoRAPipe()
    manager = GenerationManager()
    manager._pipeline = source
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._pipeline_loras = {
        "style-id": {
            "id": "style-id",
            "name": "style",
            "family": "sdxl",
            "path": str(path),
            "adapter_name": adapter_name,
            "compatibility": None,
        }
    }
    manager._active_lora_signature = ((adapter_name, 0.8),)
    manager._verified_lora_adapters = (adapter_name,)

    monkeypatch.setattr(
        manager,
        "_convert_pipeline_task",
        lambda _pipe, _family, _task: converted,
    )
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_kwargs: None)

    switched = manager._switch_loaded_pipeline_task(model, "img2img")

    assert "style-id" not in manager._pipeline_loras

    item = {
        "id": "style-id",
        "family": "sdxl",
        "name": "style",
        "path": str(path),
        "adapter_name": adapter_name,
        "weight": 0.8,
    }
    manager.configure_loras(switched, model, [item])

    assert len(converted.loads) == 1
    assert converted.loads[0]["adapter_name"] == adapter_name
    assert converted.adapter_calls == [([adapter_name], [0.8])]
    assert manager._pipeline_loras["style-id"]["adapter_name"] == adapter_name
    assert converted.get_active_adapters() == [adapter_name]



def test_adapter_diagnostics_require_real_nonzero_payload() -> None:
    class TinyAdapter(torch.nn.Module):
        def __init__(self, value: float) -> None:
            super().__init__()
            self.lora_A = torch.nn.ParameterDict(
                {
                    "morphorum_test": torch.nn.Parameter(
                        torch.full((2, 2), value, dtype=torch.float32)
                    )
                }
            )
            self.lora_B = torch.nn.ParameterDict(
                {
                    "morphorum_test": torch.nn.Parameter(
                        torch.full((2, 2), value, dtype=torch.float32)
                    )
                }
            )

    pipe = type("Pipe", (), {})()
    pipe.unet = TinyAdapter(1.0)
    manager = GenerationManager()

    diagnostics = manager._verify_adapter_weights(
        pipe,
        "morphorum_test",
        component_name="unet",
    )

    assert diagnostics["available"] is True
    assert diagnostics["modules"] >= 1
    assert diagnostics["tensors"] == 2
    assert diagnostics["parameters"] == 8
    assert diagnostics["abs_sum"] == pytest.approx(8.0)

    pipe.unet = TinyAdapter(0.0)
    with pytest.raises(GenerationError, match="no usable injected LoRA weights"):
        manager._verify_adapter_weights(
            pipe,
            "morphorum_test",
            component_name="unet",
        )


def test_sdxl_runtime_exposes_direct_unet_lora_loader_api() -> None:
    import inspect
    from diffusers import StableDiffusionXLPipeline

    parameters = inspect.signature(
        StableDiffusionXLPipeline.load_lora_into_unet
    ).parameters

    for name in (
        "state_dict",
        "network_alphas",
        "unet",
        "adapter_name",
        "_pipeline",
    ):
        assert name in parameters

@pytest.mark.parametrize("family", ["sdxl", "flux", "zimage"])
def test_animation_prepare_txt2img_and_img2img_share_lora_engine(
    family: str, tmp_path: Path, monkeypatch
) -> None:
    """Regression: animation's starting frame and subsequent frames reuse the
    same GenerationManager adapter loading/activation engine as still images.
    No GPU or model downloads required.
    """
    if family == "zimage":
        checkpoint = create_zimage_layout(tmp_path / "Z-Image-Turbo")
    else:
        checkpoint = tmp_path / "base.safetensors"
        checkpoint.write_bytes(b"fake-model")
    model = fake_model(checkpoint, family)
    lora_path = tmp_path / "CreepyDroneStyle.safetensors"
    lora_path.write_bytes(b"fake-lora")
    adapter_name = "morphorum_animation-style"
    item = {
        "id": "animation-style", "name": "CreepyDroneStyle",
        "family": family, "adapter_name": adapter_name,
        "path": str(lora_path), "weight": 0.8,
    }
    monkeypatch.setattr(generation, "get_model", lambda _model_id: model)

    class ObservablePipe(FakeTrackedLoRAPipe):
        def disable_lora(self) -> None:
            super().disable_lora()
            self.active_adapters = []

    txt2img_pipe = ObservablePipe()
    # Diffusers from_pipe() normally shares adapter-bearing components.
    img2img_pipe = ObservablePipe([adapter_name])
    manager = GenerationManager()
    manager._pipeline = txt2img_pipe
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._pipeline_device = "cpu"
    monkeypatch.setattr(
        manager, "_load_pipeline",
        lambda _job, _progress=None: (txt2img_pipe, "cpu"),
    )
    monkeypatch.setattr(
        manager, "_convert_pipeline_task",
        lambda _pipe, _family, task: img2img_pipe if task == "img2img" else txt2img_pipe,
    )
    monkeypatch.setattr(manager, "_configure_sampler", lambda *_args: None)
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_kwargs: None)

    sampler = "euler" if family == "sdxl" else "flowmatch_euler"
    guidance = 6.0 if family == "sdxl" else (1.0 if family == "flux" else 0.0)

    def request(loras):
        return GenerationRequest(
            model_id=model["id"], prompt="cinematic landscape",
            width=64, height=64, steps=5, sampler=sampler,
            guidance_scale=guidance, loras=loras,
        )

    start, _device, _model = manager.prepare_txt2img(request([item]))
    assert start is txt2img_pipe
    assert len(txt2img_pipe.loads) == 1
    assert txt2img_pipe.adapter_calls[-1] == ([adapter_name], [0.8])
    assert manager._active_lora_signature == ((adapter_name, 0.8),)

    # Animation switches to img2img for the following frame.
    after, _device, _model = manager.prepare_img2img(request([item]))
    assert after is img2img_pipe
    assert img2img_pipe.disabled == 1
    assert not img2img_pipe.loads, "The converted wrapper should reuse the injected LoRA."
    assert img2img_pipe.adapter_calls[-1] == ([adapter_name], [0.8])
    assert img2img_pipe.active_adapters == [adapter_name]

    # A subsequent keyframe changes only strength, never reloads the file.
    different = {**item, "weight": 0.35}
    manager.prepare_img2img(request([different]))
    assert len(img2img_pipe.loads) == 0
    assert img2img_pipe.adapter_calls[-1] == ([adapter_name], [0.35])

    # A frame with no LoRA has to genuinely deactivate the PEFT layers.
    manager.prepare_img2img(request([]))
    assert img2img_pipe.disabled == 2
    assert img2img_pipe.active_adapters == []
    assert manager._active_lora_signature == ()

    # A later frame can re-enable the cached adapter without reloading it.
    manager.prepare_img2img(request([item]))
    assert img2img_pipe.active_adapters == [adapter_name]
    assert len(img2img_pipe.loads) == 0


@pytest.mark.parametrize("family", ["sdxl", "flux", "zimage"])
def test_task_switch_deactivates_loras_when_next_frame_is_base_only(
    family: str, tmp_path: Path, monkeypatch
) -> None:
    """A txt2img LoRA must not contaminate a LoRA-free img2img frame."""
    path = tmp_path / "style.safetensors"
    path.write_bytes(b"fake-lora")
    model = fake_model(tmp_path / "base.safetensors", family)
    adapter_name = "morphorum-style-id"
    manager = GenerationManager()
    source = FakeTrackedLoRAPipe([adapter_name])
    converted = FakeTrackedLoRAPipe([adapter_name])
    manager._pipeline = source
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._active_lora_signature = ((adapter_name, 1.0),)
    manager._pipeline_loras = {
        "style-id": {
            "id": "style-id", "family": family, "name": "style",
            "path": str(path), "adapter_name": adapter_name,
        },
    }
    monkeypatch.setattr(
        manager, "_convert_pipeline_task",
        lambda _pipe, _family, _task: converted,
    )
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_kwargs: None)

    switched = manager._switch_loaded_pipeline_task(model, "img2img")
    assert switched is converted
    assert converted.disabled == 1
    assert manager._active_lora_signature == ()
    manager.configure_loras(switched, model, [])
    assert converted.disabled == 1, "The task switch disabled the stale active LoRA."
    assert converted.adapter_calls == []


@pytest.mark.parametrize(
    ("supports_fp8", "has_lora", "expect_fp8"),
    [
        (True, False, True),
        (True, True, False),
        (False, False, False),
        (False, True, False),
    ],
)
def test_flux_fp8_fast_path_is_gated_by_lora_use(
    supports_fp8: bool, has_lora: bool, expect_fp8: bool
) -> None:
    manager = GenerationManager()
    assert manager._flux_uses_fp8_layerwise(
        supports_fp8=supports_fp8,
        loras=[{"id": "test-lora"}] if has_lora else [],
    ) is expect_fp8


@pytest.mark.parametrize("task", ["txt2img", "img2img"])
def test_flux_lora_request_reloads_cached_fp8_pipeline_before_adapter_loading(
    task: str, tmp_path: Path, monkeypatch
) -> None:
    """Base Flux can keep FP8. A new LoRA must reload *original* BF16
    transformer weights rather than attempting PEFT over the existing FP8
    casted linears, which can cause addmm_cuda(Float8_e4m3fn).
    """
    checkpoint = tmp_path / "artsyDream_v6FP8.safetensors"
    checkpoint.write_bytes(b"fake-flux-weights")
    model = fake_model(checkpoint, "flux", "dev")
    item = {"id": "unsettling", "family": "flux", "weight": 1.0}
    request = GenerationRequest(
        model_id=model["id"], prompt="haunted mansion",
        sampler="flowmatch_euler", guidance_scale=1.0,
        loras=[item],
    )
    job = GenerationJob(id="flux-adapter", request=request, model=model)
    old_pipe = SimpleNamespace(scheduler=SimpleNamespace(config={"kind": "fake"}))
    new_pipe = SimpleNamespace(scheduler=SimpleNamespace(config={"kind": "fake"}))
    manager = GenerationManager()
    manager._pipeline = old_pipe
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._pipeline_device = "cuda-offload"
    manager._pipeline_optimization = "fp8-layerwise-bf16-compute+streamed-group-offload"
    manager._pipeline_loras = {"stale": {"adapter_name": "stale"}}
    manager._active_lora_signature = (("stale", 0.7),)
    loads: list[list[dict]] = []

    def load_flux(loaded_job, _cache_dir):
        loads.append(list(loaded_job.request.loras))
        manager._pipeline_optimization = "bf16-cpu-offload+streamed-group-offload"
        return new_pipe, "cuda-offload", "cpu"

    monkeypatch.setattr(manager, "_load_flux_pipeline", load_flux)
    monkeypatch.setattr(
        manager, "_convert_pipeline_task",
        lambda pipe, _family, _task: pipe,
    )
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_kwargs: None)

    if task == "txt2img":
        pipe, device = manager._load_pipeline(job)
    else:
        pipe, device = manager._load_img2img_pipeline(job)

    assert pipe is new_pipe
    assert device == "cpu"
    assert loads == [[item]]
    assert manager._pipeline is new_pipe
    assert manager._pipeline_loras == {}
    assert manager._active_lora_signature == ()
    assert manager._pipeline_optimization == "bf16-cpu-offload+streamed-group-offload"


def test_flux_without_lora_reuses_fp8_base_pipeline(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "artsyDream_v6FP8.safetensors"
    checkpoint.write_bytes(b"fake-flux-weights")
    model = fake_model(checkpoint, "flux", "dev")
    manager = GenerationManager()
    pipe = SimpleNamespace(scheduler=SimpleNamespace(config={"kind": "fake"}))
    manager._pipeline = pipe
    manager._pipeline_model_id = model["id"]
    manager._pipeline_device = "cuda-offload"
    manager._pipeline_task = "txt2img"
    manager._pipeline_optimization = "fp8-layerwise-bf16-compute+streamed-group-offload"
    monkeypatch.setattr(manager, "_load_flux_pipeline", lambda *_args: pytest.fail("unexpected reload"))

    job = GenerationJob(
        id="flux-base",
        request=GenerationRequest(
            model_id=model["id"], prompt="forest",
            sampler="flowmatch_euler", guidance_scale=1.0,
        ),
        model=model,
    )
    got, device = manager._load_pipeline(job)
    assert got is pipe
    assert device == "cpu"
    assert manager._pipeline_optimization.startswith("fp8-layerwise")


def test_flux_lora_safe_bf16_pipeline_is_reused(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "artsyDream_v6FP8.safetensors"
    checkpoint.write_bytes(b"fake-flux-weights")
    model = fake_model(checkpoint, "flux", "dev")
    manager = GenerationManager()
    pipe = SimpleNamespace(scheduler=SimpleNamespace(config={"kind": "fake"}))
    manager._pipeline = pipe
    manager._pipeline_model_id = model["id"]
    manager._pipeline_device = "cuda-offload"
    manager._pipeline_task = "txt2img"
    manager._pipeline_optimization = "bf16-cpu-offload+streamed-group-offload"
    monkeypatch.setattr(manager, "_load_flux_pipeline", lambda *_args: pytest.fail("unexpected reload"))

    job = GenerationJob(
        id="flux-lora",
        request=GenerationRequest(
            model_id=model["id"], prompt="forest",
            sampler="flowmatch_euler", guidance_scale=1.0,
            loras=[{"id": "style", "family": "flux", "weight": 1.0}],
        ),
        model=model,
    )
    got, device = manager._load_pipeline(job)
    assert got is pipe
    assert device == "cpu"

@pytest.mark.parametrize(
    ("vram_gib", "with_lora", "stream_expected"),
    [
        (8, False, False), (16, False, False), (16, True, False),
        (24, False, False), (24, True, False),
        (32, False, True), (32, True, False),
        (48, True, True),
    ],
)
def test_flux_streaming_offload_avoids_pinning_on_small_vram(
    vram_gib: int, with_lora: bool, stream_expected: bool
) -> None:
    assert GenerationManager._flux_streaming_offload_enabled(
        vram_bytes=vram_gib * 1024**3,
        with_lora=with_lora,
    ) is stream_expected


@pytest.mark.parametrize("has_lora", [False, True])
def test_flux_16gib_loader_never_streams_cpu_group_offload(
    tmp_path: Path, monkeypatch, has_lora: bool
) -> None:
    """Exercise actual Flux loader configuration without CUDA or large weights.

    Diffusers streamed hooks pin tensors using cuMemHostAlloc; our RTX 4080
    SUPER path must avoid them even for plain Flux inference.
    """
    from types import SimpleNamespace
    import torch
    import diffusers
    import diffusers.hooks

    tracker: dict = {"calls": [], "dtype": [], "fp8": []}
    transformer = SimpleNamespace()
    transformer.enable_layerwise_casting = lambda **kwargs: tracker["fp8"].append(kwargs)

    class FakeFluxTransformer:
        @staticmethod
        def from_single_file(_path, **kwargs):
            tracker["dtype"].append(kwargs["torch_dtype"])
            return transformer

    class FakeFluxPipeline:
        @staticmethod
        def from_pretrained(_repo, **kwargs):
            assert kwargs["transformer"] is transformer
            assert kwargs["torch_dtype"] == torch.bfloat16
            return SimpleNamespace(
                transformer=transformer,
                text_encoder=SimpleNamespace(),
                text_encoder_2=SimpleNamespace(),
                vae=SimpleNamespace(),
                set_progress_bar_config=lambda **_kwargs: None,
            )

    monkeypatch.setattr(diffusers, "FluxTransformer2DModel", FakeFluxTransformer)
    monkeypatch.setattr(diffusers, "FluxPipeline", FakeFluxPipeline)
    monkeypatch.setattr(
        diffusers.hooks, "apply_group_offloading",
        lambda component, **kwargs: tracker["calls"].append(
            (component, kwargs.copy())
        ),
    )
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_capability", lambda _idx: (8, 9))
    monkeypatch.setattr(
        torch.cuda, "get_device_properties",
        lambda _idx: SimpleNamespace(total_memory=16 * 1024**3),
    )

    model_path = tmp_path / "artsyDream_v6FP8.safetensors"
    model_path.write_bytes(b"fake")
    model = fake_model(model_path, "flux", "dev")
    job = GenerationJob(
        id="flux-no-stream",
        request=GenerationRequest(
            model_id=model["id"], prompt="haunted house",
            loras=[{"id": "test-flux-lora"}] if has_lora else [],
            sampler="flowmatch_euler", guidance_scale=1.0,
        ),
        model=model,
    )
    manager = GenerationManager()
    pipe, location, gen_device = manager._load_flux_pipeline(job, tmp_path)
    assert location == "cuda-offload"
    assert gen_device == "cpu"
    assert pipe.transformer is transformer
    assert len(tracker["calls"]) == 4
    assert all(not kwargs["use_stream"] for _, kwargs in tracker["calls"])
    assert tracker["calls"][0][1]["offload_type"] == "block_level"
    assert tracker["calls"][0][1]["num_blocks_per_group"] == 1
    assert manager.pipeline_optimization().endswith("+nonstreamed-group-offload")
    assert len(tracker["fp8"]) == (0 if has_lora else 1)


def test_flux_out_of_memory_during_offload_never_retries_partially_hooked_model(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace
    import torch
    import diffusers
    import diffusers.hooks

    calls = []
    transformer = SimpleNamespace(enable_layerwise_casting=lambda **_kw: None)
    monkeypatch.setattr(diffusers, "FluxTransformer2DModel", SimpleNamespace(
        from_single_file=lambda *_args, **_kw: transformer,
    ))
    monkeypatch.setattr(diffusers, "FluxPipeline", SimpleNamespace(
        from_pretrained=lambda *_args, **_kw: SimpleNamespace(
            transformer=transformer, text_encoder=None, text_encoder_2=None,
            vae=None, set_progress_bar_config=lambda **_kw: None,
        ),
    ))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: True)
    monkeypatch.setattr(torch.cuda, "get_device_capability", lambda _idx: (8, 9))
    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda _idx:
                        SimpleNamespace(total_memory=16 * 1024**3))

    def fail_once(_component, **kwargs):
        calls.append(kwargs.copy())
        raise RuntimeError("CUDA error: out of memory while preparing offload hooks")

    monkeypatch.setattr(diffusers.hooks, "apply_group_offloading", fail_once)
    model_path = tmp_path / "flux.safetensors"
    model_path.write_bytes(b"fake")
    model = fake_model(model_path, "flux", "dev")
    job = GenerationJob(
        id="flux-hook-fail",
        request=GenerationRequest(
            model_id=model["id"], prompt="test",
            sampler="flowmatch_euler", guidance_scale=1.0,
        ),
        model=model,
    )
    manager = GenerationManager()
    with pytest.raises(GenerationError, match="GPU memory exhausted"):
        manager._load_flux_pipeline(job, tmp_path)
    assert len(calls) == 1, "Never retry after an offload CUDA OOM"
    assert calls[0]["use_stream"] is False


def test_sdxl_transition_profile_stages_and_sharing(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "model.safetensors"
    checkpoint.write_bytes(b"fake")
    model = fake_model(checkpoint, "sdxl")
    original = FakeTrackedLoRAPipe([])
    converted = FakeTrackedLoRAPipe([])
    shared_unet = object()
    shared_vae = object()
    original.unet, converted.unet = shared_unet, shared_unet
    original.vae, converted.vae = shared_vae, shared_vae
    manager = GenerationManager()
    manager._pipeline = original
    manager._pipeline_model_id = model["id"]
    manager._pipeline_task = "txt2img"
    manager._pipeline_device = "cuda"

    snapshots = iter([6.89, 13.76, 13.76, 13.76, 13.76])
    def fake_memory():
        v = next(snapshots)
        return {
            "allocated_gib": v, "reserved_gib": v + 0.1,
            "free_gib": 15.99 - v, "allocation_retries": 0, "oom_count": 0,
        }

    monkeypatch.setattr(manager, "cuda_memory_status", fake_memory)
    monkeypatch.setattr(manager, "_convert_pipeline_task", lambda *_: converted)
    monkeypatch.setattr(manager, "release_inference_memory", lambda **_: None)
    monkeypatch.setattr(manager, "_configure_sampler", lambda *_: None)
    monkeypatch.setattr(manager, "configure_loras", lambda *_: [])
    monkeypatch.setattr(generation, "get_model", lambda _: model)

    request = GenerationRequest(
        model_id=model["id"], prompt="test", width=64, height=64,
        steps=5, sampler="euler",
    )
    result, _, _ = manager.prepare_img2img(request)
    assert result is converted
    profile = manager.model_status()["sdxl_transition_profile"]
    assert profile["complete"] is True
    assert [p["stage"] for p in profile["stages"]] == [
        "before_conversion", "after_from_pipe", "after_release",
        "after_sampler", "after_lora_setup",
    ]
    assert profile["stages"][0]["allocated_gib"] == 6.89
    assert profile["stages"][1]["allocated_gib"] == 13.76
    assert profile["shared_components"] == {"unet": True, "vae": True}
    manager.prepare_img2img(request)
    assert manager.model_status()["sdxl_transition_profile"] == profile


def test_sdxl_component_identity_inspection_skips_missing_components() -> None:
    assert GenerationManager._shared_pipeline_components(
        SimpleNamespace(unet=object()), SimpleNamespace()
    ) == {}


@pytest.mark.parametrize("precision", [torch.float16, torch.float32])
def test_sdxl_task_conversion_preserves_loaded_unet_precision(monkeypatch, precision) -> None:
    """Regression for Diffusers 0.40.0 from_pipe() implicit float32 upcast."""
    import diffusers

    kwargs_seen = []

    class FakeConverted:
        @classmethod
        def from_pipe(cls, original, **kwargs):
            kwargs_seen.append((original, kwargs))
            return cls()

        def set_progress_bar_config(self, **kwargs):
            self.progress = kwargs

    monkeypatch.setattr(diffusers, "StableDiffusionXLImg2ImgPipeline", FakeConverted)
    pipe = SimpleNamespace(unet=SimpleNamespace(dtype=precision))
    converted = GenerationManager()._convert_pipeline_task(pipe, "sdxl", "img2img")
    assert isinstance(converted, FakeConverted)
    assert kwargs_seen == [(pipe, {"dtype": precision})]
    assert converted.progress == {"disable": True}


def test_sdxl_task_conversion_requires_explicit_source_precision(monkeypatch) -> None:
    """Missing dtype must never silently convert a live FP16 model to FP32."""
    import diffusers

    class UnexpectedConversion:
        @classmethod
        def from_pipe(cls, *_args, **_kwargs):
            raise AssertionError("from_pipe must not be invoked without SDXL dtype")

    monkeypatch.setattr(diffusers, "StableDiffusionXLImg2ImgPipeline", UnexpectedConversion)
    with pytest.raises(GenerationError, match="Cannot determine.*SDXL UNet precision"):
        GenerationManager()._convert_pipeline_task(
            SimpleNamespace(unet=SimpleNamespace()), "sdxl", "img2img"
        )
