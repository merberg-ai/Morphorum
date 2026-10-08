from __future__ import annotations

from pathlib import Path

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

    def delete_adapters(self, adapter_name):
        self.deleted.append(adapter_name)
        self.peft_config.pop(adapter_name, None)


class FakeSDXLRankBugPipe(FakeLoRAPipe):
    def __init__(self, *, partial_unet: bool = False) -> None:
        super().__init__()
        self.partial_unet = partial_unet
        self.unet = FakeRankBugUNet()
        self.unet_loads = []

    def load_lora_weights(self, source, **kwargs):
        self.loads.append({"path": source, **kwargs})
        adapter_name = kwargs.get("adapter_name")
        if self.partial_unet and adapter_name:
            self.unet.peft_config[adapter_name] = object()
        raise IndexError("list index out of range")

    def lora_state_dict(self, *_args, **_kwargs):
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
