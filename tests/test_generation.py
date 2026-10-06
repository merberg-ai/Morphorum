from __future__ import annotations

from pathlib import Path

import pytest

import morphorum.generation as generation
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
