from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

import morphorum.animation_render as animation_render
from morphorum.animation_resolution import resolve_project_frame
from morphorum.animation_render import (
    AnimationRenderJob,
    AnimationRenderManager,
    _blend_value,
    _prompt_conditioning_kwargs,
    _prompt_state_for_frame,
)


def sample_project(max_frames: int = 4) -> dict:
    return {
        "schema_version": 1,
        "id": "render-test",
        "name": "Render Test",
        "animation": {
            "max_frames": max_frames,
            "fps": 12.0,
            "width": 64,
            "height": 64,
            "prompt_transition": "blend",
            "start_mode": "source",
            "source_image": "assets/source.png",
            "source_image_name": "source.png",
        },
        "model": {
            "model_id": "fake-model",
            "family": "sdxl",
            "variant": "sdxl",
        },
        "prompts": {
            "0": "forest",
            str(max_frames - 1): "city",
        },
        "negative_prompts": {"0": ""},
        "motion": {
            "angle": "0:(0)",
            "zoom": "0:(1.0)",
            "translation_x": "0:(1)",
            "translation_y": "0:(0)",
            "border_mode": "replicate",
        },
        "generation": {
            "strength": "0:(1)",
            "noise": "0:(0)",
            "steps": "0:(5)",
            "guidance": "0:(6)",
            "sampler": "euler",
            "seed": 100,
            "seed_behavior": "increment",
            "seed_increment": 1,
        },
        "notes": "",
    }


def fake_model() -> dict:
    return {
        "id": "fake-model",
        "family": "sdxl",
        "variant": "sdxl",
        "kind": "checkpoints",
        "name": "Fake SDXL",
        "filename": "fake.safetensors",
        "path": "fake.safetensors",
        "extension": ".safetensors",
        "source": "external",
    }


def wait_for(manager: AnimationRenderManager, render_id: str) -> dict:
    job = None
    for _ in range(200):
        job = manager.get(render_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.025)
    raise AssertionError(f"render did not finish: {job}")


def test_strength_one_render_persists_frames_manifest_and_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    source = tmp_path / "source.png"
    image = Image.new("RGB", (64, 64), "black")
    for x in range(16, 32):
        for y in range(20, 44):
            image.putpixel((x, y), (255, 128, 0))
    image.save(source)

    manager = AnimationRenderManager()
    started = manager.submit(project=sample_project(), source_path=source)
    finished = wait_for(manager, started["id"])

    assert finished["status"] == "completed", finished
    assert finished["progress"] == 1.0
    assert len(finished["results"]) == 4
    assert finished["preview_url"]
    assert finished["latest_frame_url"]

    render_dir = (
        tmp_path / "outputs" / "animations" / "render-test" / started["id"]
    )
    assert (render_dir / "source.png").is_file()
    assert (render_dir / "preview.gif").is_file()
    for frame in range(4):
        assert (render_dir / "frames" / f"frame_{frame:06d}.png").is_file()

    manifest = json.loads(
        (render_dir / "render-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert manifest["status"] == "completed"
    assert manifest["seed_plan"] == [100, 101, 102, 103]
    assert manifest["project"]["name"] == "Render Test"

    with Image.open(render_dir / "frames" / "frame_000003.png") as final:
        assert final.size == (64, 64)


def test_interrupted_manifest_can_resume_from_last_completed_frame(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "orange").save(source)

    first_manager = AnimationRenderManager()
    started = first_manager.submit(project=sample_project(), source_path=source)
    completed = wait_for(first_manager, started["id"])
    assert completed["status"] == "completed"

    render_dir = (
        tmp_path / "outputs" / "animations" / "render-test" / started["id"]
    )
    manifest_path = render_dir / "render-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "rendering"
    manifest["message"] = "process died here"
    manifest["results"] = [
        item for item in manifest["results"] if int(item["frame"]) <= 1
    ]
    manifest["current_frame"] = 1
    manifest["progress"] = 0.5
    manifest["preview"] = None
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    for frame in (2, 3):
        (render_dir / "frames" / f"frame_{frame:06d}.png").unlink()
    (render_dir / "preview.gif").unlink()

    second_manager = AnimationRenderManager()
    listed = second_manager.list_project("render-test")
    stale = next(item for item in listed if item["id"] == started["id"])
    assert stale["status"] == "interrupted"
    assert stale["resumable"] is True

    resumed = second_manager.resume("render-test", started["id"])
    assert resumed["resumed"] is True
    finished = wait_for(second_manager, started["id"])
    assert finished["status"] == "completed"
    assert len(finished["results"]) == 4
    assert (render_dir / "frames" / "frame_000003.png").is_file()


class FakeSDXLPipe:
    def encode_prompt(
        self,
        *,
        prompt,
        negative_prompt=None,
        num_images_per_prompt=1,
        do_classifier_free_guidance=True,
    ):
        values = {
            "forest": 0.0,
            "city": 10.0,
            "bad": -2.0,
            "worse": -6.0,
            "": 0.0,
            None: 0.0,
        }
        positive = torch.tensor([values[prompt]], dtype=torch.float32)
        negative = (
            torch.tensor([values[negative_prompt]], dtype=torch.float32)
            if do_classifier_free_guidance
            else None
        )
        pooled = positive + 100
        negative_pooled = negative + 100 if negative is not None else None
        return positive, negative, pooled, negative_pooled


def test_sdxl_prompt_conditioning_blends_positive_and_negative_embeddings() -> None:
    kwargs = _prompt_conditioning_kwargs(
        FakeSDXLPipe(),
        "sdxl",
        {
            "from_frame": 0,
            "to_frame": 10,
            "from_text": "forest",
            "to_text": "city",
            "from_weight": 0.75,
            "to_weight": 0.25,
        },
        {
            "from_frame": 0,
            "to_frame": 10,
            "from_text": "bad",
            "to_text": "worse",
            "from_weight": 0.5,
            "to_weight": 0.5,
        },
        guidance_scale=6.0,
    )

    assert kwargs["prompt"] is None
    assert kwargs["prompt_embeds"].item() == pytest.approx(2.5)
    assert kwargs["pooled_prompt_embeds"].item() == pytest.approx(102.5)
    assert kwargs["negative_prompt_embeds"].item() == pytest.approx(-4.0)
    assert kwargs["negative_pooled_prompt_embeds"].item() == pytest.approx(96.0)


def test_img2img_runtime_classes_expose_required_api() -> None:
    import inspect

    from diffusers import (
        FluxImg2ImgPipeline,
        StableDiffusionXLImg2ImgPipeline,
        ZImageImg2ImgPipeline,
    )

    for pipeline_class in (
        StableDiffusionXLImg2ImgPipeline,
        FluxImg2ImgPipeline,
        ZImageImg2ImgPipeline,
    ):
        assert callable(getattr(pipeline_class, "from_pipe", None))
        parameters = inspect.signature(pipeline_class.__call__).parameters
        for name in (
            "prompt",
            "image",
            "strength",
            "num_inference_steps",
            "guidance_scale",
            "generator",
            "callback_on_step_end",
        ):
            assert name in parameters


    sdxl_encode = inspect.signature(
        StableDiffusionXLImg2ImgPipeline.encode_prompt
    ).parameters
    assert "negative_prompt" in sdxl_encode
    assert "do_classifier_free_guidance" in sdxl_encode

    flux_encode = inspect.signature(
        FluxImg2ImgPipeline.encode_prompt
    ).parameters
    assert "pooled_prompt_embeds" in flux_encode
    assert "max_sequence_length" in flux_encode

    zimage_encode = inspect.signature(
        ZImageImg2ImgPipeline.encode_prompt
    ).parameters
    assert "do_classifier_free_guidance" in zimage_encode
    assert "max_sequence_length" in zimage_encode


def test_uniform_noise_is_deterministic() -> None:
    from morphorum.animation_render import _add_uniform_noise

    source = Image.new("RGB", (8, 8), "gray")
    first = _add_uniform_noise(source, amount=0.02, seed=123)
    second = _add_uniform_noise(source, amount=0.02, seed=123)
    third = _add_uniform_noise(source, amount=0.02, seed=124)

    assert first.tobytes() == second.tobytes()
    assert first.tobytes() != third.tobytes()


def test_latest_frame_url_tracks_last_completed_result() -> None:
    job = AnimationRenderJob(
        id="anim-test",
        project_id="project-test",
        project={},
        seed_plan=[1, 2, 3],
        total_frames=3,
        current_frame=2,
        results=[
            {"frame": 0, "path": "0.png"},
            {"frame": 1, "path": "1.png"},
        ],
    )
    public = job.public()
    assert public["latest_completed_frame"] == 1
    assert public["latest_frame_url"].endswith("/frames/1")


def test_variable_length_tensor_blend_zero_pads_sequence_dimension() -> None:
    left = torch.ones((2, 3), dtype=torch.float32)
    right = torch.full((4, 3), 3.0, dtype=torch.float32)

    blended = _blend_value(left, right, 0.25)

    assert blended.shape == (4, 3)
    assert torch.allclose(blended[:2], torch.full((2, 3), 1.5))
    assert torch.allclose(blended[2:], torch.full((2, 3), 0.75))


class FakePromptStartPipe:
    def set_progress_bar_config(self, **_kwargs):
        return None

    def __call__(self, **_kwargs):
        return SimpleNamespace(images=[Image.new("RGB", (64, 64), "purple")])


class FakePromptStartGenerationManager:
    def __init__(self) -> None:
        self.inference_lock = threading.Lock()
        self.pipe = FakePromptStartPipe()

    def _effective_capability(self, _model):
        return {}

    def prepare_txt2img(self, _request, load_progress_callback=None):
        if load_progress_callback is not None:
            load_progress_callback(1.0, "ready", "Fake pipeline ready", "test")
        return self.pipe, "cpu", fake_model()

    def build_txt2img_call_args(
        self,
        request,
        _model,
        *,
        generator,
        on_step_end,
    ):
        self.img2img_strengths.append(float(strength))
        return {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt or None,
            "generator": generator,
            "callback_on_step_end": on_step_end,
        }

    def _model_variant(self, _model):
        return "sdxl"

    def unload_after_job_enabled(self):
        return False

    def reset_inference_pipeline(self):
        return None

    def pipeline_optimization(self):
        return None

    def release_inference_memory(self, **_kwargs):
        return None

    def cuda_memory_status(self):
        return None

    def _is_cuda_oom(self, _exc):
        return False

    def _friendly_error(self, exc, **_kwargs):
        return exc


def test_prompt_start_mode_generates_frame_zero_without_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(
        animation_render,
        "generation_manager",
        FakePromptStartGenerationManager(),
    )
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    project = sample_project(max_frames=1)
    project["animation"]["start_mode"] = "prompt"
    project["animation"]["source_image"] = ""
    project["animation"]["source_image_name"] = ""

    manager = AnimationRenderManager()
    started = manager.submit(
        project=project,
        source_path=tmp_path / "does-not-exist.png",
    )
    finished = wait_for(manager, started["id"])

    assert finished["status"] == "completed", finished
    assert finished["latest_completed_frame"] == 0
    frame = (
        tmp_path
        / "outputs"
        / "animations"
        / "render-test"
        / started["id"]
        / "frames"
        / "frame_000000.png"
    )
    assert frame.is_file()
    with Image.open(frame) as generated:
        assert generated.getpixel((0, 0)) == (128, 0, 128)


def test_source_start_mode_requires_uploaded_image(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    manager = AnimationRenderManager()

    with pytest.raises(
        animation_render.AnimationRenderError,
        match="no starting image",
    ):
        manager.submit(
            project=sample_project(max_frames=1),
            source_path=tmp_path / "missing.png",
        )


class FakeZImageBlendPipe:
    def encode_prompt(
        self,
        *,
        prompt,
        do_classifier_free_guidance=False,
        max_sequence_length=512,
    ):
        del do_classifier_free_guidance, max_sequence_length
        if prompt == "short prompt":
            embeds = [torch.ones((2, 3), dtype=torch.float32)]
        else:
            embeds = [torch.full((4, 3), 3.0, dtype=torch.float32)]
        return embeds, []


def test_zimage_prompt_transition_blends_unequal_sequence_lengths() -> None:
    kwargs = _prompt_conditioning_kwargs(
        FakeZImageBlendPipe(),
        "zimage",
        {
            "from_frame": 0,
            "to_frame": 10,
            "from_text": "short prompt",
            "to_text": "a much longer prompt",
            "from_weight": 0.75,
            "to_weight": 0.25,
        },
        {
            "from_frame": 0,
            "to_frame": 0,
            "from_text": "",
            "to_text": "",
            "from_weight": 1.0,
            "to_weight": 0.0,
        },
        guidance_scale=0.0,
    )

    assert kwargs["prompt"] is None
    assert isinstance(kwargs["prompt_embeds"], list)
    blended = kwargs["prompt_embeds"][0]
    assert blended.shape == (4, 3)
    assert torch.allclose(blended[:2], torch.full((2, 3), 1.5))
    assert torch.allclose(blended[2:], torch.full((2, 3), 0.75))


def test_zimage_conditioning_cache_encodes_each_keyframe_once() -> None:
    class CountingPipe(FakeZImageBlendPipe):
        def __init__(self):
            self.calls = []

        def encode_prompt(self, **kwargs):
            self.calls.append(kwargs["prompt"])
            return super().encode_prompt(**kwargs)

    pipe = CountingPipe()
    cache = {}
    positive = {
        "from_frame": 0,
        "to_frame": 10,
        "from_text": "short prompt",
        "to_text": "a much longer prompt",
        "from_weight": 0.75,
        "to_weight": 0.25,
    }
    negative = {
        "from_frame": 0,
        "to_frame": 0,
        "from_text": "",
        "to_text": "",
        "from_weight": 1.0,
        "to_weight": 0.0,
    }

    first = _prompt_conditioning_kwargs(
        pipe,
        "zimage",
        positive,
        negative,
        guidance_scale=0.0,
        conditioning_cache=cache,
        cache_zimage_on_cpu=True,
    )
    second = _prompt_conditioning_kwargs(
        pipe,
        "zimage",
        positive,
        negative,
        guidance_scale=0.0,
        conditioning_cache=cache,
        cache_zimage_on_cpu=True,
    )

    assert pipe.calls == ["short prompt", "a much longer prompt"]
    assert len(cache) == 2
    assert first["prompt_embeds"][0].device.type == "cpu"
    assert second["prompt_embeds"][0].device.type == "cpu"


def test_animation_job_exposes_model_load_progress() -> None:
    job = AnimationRenderJob(
        id="load-test",
        project_id="project",
        project={},
        seed_plan=[1],
        total_frames=1,
        status="loading_model",
        load_progress=0.68,
        load_phase="pipeline",
        load_message="Pipeline components loaded",
        load_detail="7 local safetensors files",
    )
    public = job.public()
    assert public["load_progress"] == pytest.approx(0.68)
    assert public["load_phase"] == "pipeline"
    assert "safetensors" in public["load_detail"]



def test_render_prompt_telemetry_matches_resolved_frame_transition() -> None:
    project = sample_project(max_frames=4)
    resolved = resolve_project_frame(project, 1)
    telemetry = _prompt_state_for_frame(resolved, applied=True)

    assert telemetry["frame"] == 1
    assert telemetry["applied"] is True
    assert telemetry["positive"]["from_frame"] == 0
    assert telemetry["positive"]["to_frame"] == 3
    assert telemetry["positive"]["from_text"] == "forest"
    assert telemetry["positive"]["to_text"] == "city"
    assert telemetry["positive"]["from_weight"] == pytest.approx(2 / 3)
    assert telemetry["positive"]["to_weight"] == pytest.approx(1 / 3)


def test_animation_job_public_exposes_current_prompt_telemetry() -> None:
    resolved = resolve_project_frame(sample_project(max_frames=4), 2)
    prompt_state = _prompt_state_for_frame(
        resolved,
        applied=False,
        reason="Retention strength is 1.0, so this frame skips diffusion.",
    )
    job = AnimationRenderJob(
        id="prompt-state",
        project_id="project",
        project={},
        seed_plan=[1, 2, 3, 4],
        total_frames=4,
        current_frame=2,
        current_prompt_state=prompt_state,
    )

    public = job.public()

    assert public["current_prompt_state"]["frame"] == 2
    assert public["current_prompt_state"]["applied"] is False
    assert "skips diffusion" in public["current_prompt_state"]["reason"]
    assert public["current_prompt_state"]["positive"]["to_text"] == "city"



class RecordingSDXLPipe(FakeSDXLPipe):
    def __init__(self) -> None:
        self.conditioning = []

    def __call__(self, **kwargs):
        if kwargs.get("prompt_embeds") is not None:
            self.conditioning.append(
                ("embeds", float(kwargs["prompt_embeds"].reshape(-1)[0].item()))
            )
        else:
            self.conditioning.append(("prompt", kwargs.get("prompt")))
        return SimpleNamespace(images=[Image.new("RGB", (64, 64), "blue")])


class RecordingSDXLGenerationManager:
    def __init__(self) -> None:
        self.inference_lock = threading.Lock()
        self.pipe = RecordingSDXLPipe()
        self.requests = []
        self.img2img_strengths = []

    def _effective_capability(self, _model):
        return {"max_sequence_length": 512}

    def prepare_img2img(self, _request, load_progress_callback=None):
        self.requests.append(_request)
        if load_progress_callback is not None:
            load_progress_callback(1.0, "ready", "Fake img2img ready", "test")
        return self.pipe, "cpu", fake_model()

    def build_img2img_call_args(
        self,
        request,
        _model,
        *,
        image,
        strength,
        generator,
        on_step_end,
    ):
        return {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt or None,
            "image": image,
            "strength": strength,
            "generator": generator,
            "callback_on_step_end": on_step_end,
        }

    def _model_variant(self, _model):
        return "sdxl"

    def unload_after_job_enabled(self):
        return False

    def reset_inference_pipeline(self):
        return None

    def pipeline_optimization(self):
        return None

    def release_inference_memory(self, **_kwargs):
        return None

    def cuda_memory_status(self):
        return None

    def _is_cuda_oom(self, _exc):
        return False

    def _friendly_error(self, exc, **_kwargs):
        return exc


def test_render_loop_changes_sdxl_prompt_conditioning_across_keyframes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_generation = RecordingSDXLGenerationManager()
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(animation_render, "generation_manager", fake_generation)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "orange").save(source)

    project = sample_project(max_frames=4)
    project["generation"]["strength"] = "0:(0.5)"
    manager = AnimationRenderManager()
    started = manager.submit(project=project, source_path=source)
    finished = wait_for(manager, started["id"])

    assert finished["status"] == "completed", finished
    assert fake_generation.pipe.conditioning[0][0] == "embeds"
    assert fake_generation.pipe.conditioning[0][1] == pytest.approx(10 / 3)
    assert fake_generation.pipe.conditioning[1][0] == "embeds"
    assert fake_generation.pipe.conditioning[1][1] == pytest.approx(20 / 3)
    assert fake_generation.pipe.conditioning[2] == ("prompt", "city")
    assert finished["current_prompt_state"]["frame"] == 3
    assert finished["current_prompt_state"]["positive"]["from_text"] == "city"



def test_render_loop_applies_full_2d_and_generation_schedule_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_generation = RecordingSDXLGenerationManager()
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(animation_render, "generation_manager", fake_generation)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    real_render_affine = animation_render.render_affine
    real_add_noise = animation_render._add_uniform_noise
    motion_calls = []
    noise_calls = []

    def recording_render_affine(source, matrix, *, border_mode):
        motion_calls.append((matrix.copy(), border_mode))
        return real_render_affine(source, matrix, border_mode=border_mode)

    def recording_add_noise(image, *, amount, seed):
        noise_calls.append((float(amount), int(seed)))
        return real_add_noise(image, amount=amount, seed=seed)

    monkeypatch.setattr(animation_render, "render_affine", recording_render_affine)
    monkeypatch.setattr(animation_render, "_add_uniform_noise", recording_add_noise)

    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "orange").save(source)

    project = sample_project(max_frames=4)
    project["motion"].update(
        {
            "angle": "0:(0), 3:(3)",
            "zoom": "0:(1.0), 3:(1.03)",
            "translation_x": "0:(0), 3:(6)",
            "translation_y": "0:(0), 3:(-3)",
            "border_mode": "wrap",
        }
    )
    project["generation"].update(
        {
            "strength": "0:(0.8), 3:(0.5)",
            "noise": "0:(0.0), 3:(0.03)",
            "steps": "0:(6), 3:(9)",
            "guidance": "0:(4), 3:(7)",
            "seed": 100,
            "seed_behavior": "increment",
            "seed_increment": 1,
        }
    )

    manager = AnimationRenderManager()
    started = manager.submit(project=project, source_path=source)
    finished = wait_for(manager, started["id"])

    assert finished["status"] == "completed", finished
    assert len(motion_calls) == 3
    assert [mode for _matrix, mode in motion_calls] == ["wrap", "wrap", "wrap"]

    for index, frame in enumerate((1, 2, 3)):
        expected = animation_render._frame_transform_matrix(
            width=64,
            height=64,
            angle=float(frame),
            zoom=1.0 + frame * 0.01,
            translation_x=float(frame * 2),
            translation_y=float(-frame),
        )
        assert np.allclose(motion_calls[index][0], expected)

    assert fake_generation.img2img_strengths == pytest.approx([0.3, 0.4, 0.5])
    assert [request.steps for request in fake_generation.requests] == [7, 8, 9]
    assert [request.guidance_scale for request in fake_generation.requests] == pytest.approx(
        [5.0, 6.0, 7.0]
    )
    assert [request.seed for request in fake_generation.requests] == [101, 102, 103]
    assert noise_calls == pytest.approx(
        [(0.01, 101), (0.02, 102), (0.03, 103)]
    )

    state = finished["current_frame_state"]
    assert state["frame"] == 3
    assert state["motion_applied"] is True
    assert state["motion"]["angle"] == pytest.approx(3.0)
    assert state["motion"]["zoom"] == pytest.approx(1.03)
    assert state["motion"]["translation_x"] == pytest.approx(6.0)
    assert state["motion"]["translation_y"] == pytest.approx(-3.0)
    assert state["motion"]["border_mode"] == "wrap"
    assert state["cumulative_2d"]["zoom"] == pytest.approx(1.01 * 1.02 * 1.03)
    assert state["cumulative_2d"]["rotation_degrees"] == pytest.approx(6.0)
    assert state["generation"]["strength"] == pytest.approx(0.5)
    assert state["generation"]["denoise_strength"] == pytest.approx(0.5)
    assert state["generation"]["noise"] == pytest.approx(0.03)
    assert state["generation"]["steps"] == 9
    assert state["generation"]["guidance"] == pytest.approx(7.0)
    assert state["generation"]["seed"] == 103
    assert state["generation"]["seed_behavior"] == "increment"
    assert state["generation"]["seed_increment"] == 1
    assert state["generation"]["diffusion_mode"] == "img2img"

    frame_path = (
        tmp_path
        / "outputs"
        / "animations"
        / "render-test"
        / started["id"]
        / "frames"
        / "frame_000003.png"
    )
    with Image.open(frame_path) as rendered:
        metadata = json.loads(rendered.text["Morphorum"])
    assert metadata["render_state"]["frame"] == 3
    assert metadata["render_state"]["cumulative_2d"]["zoom"] == pytest.approx(
        1.01 * 1.02 * 1.03
    )


def test_source_frame_telemetry_marks_motion_and_diffusion_not_applied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(animation_render, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(animation_render, "get_model", lambda _model_id: fake_model())
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_DIMENSION", 64)
    monkeypatch.setattr(animation_render, "PREVIEW_MAX_FRAMES", 8)

    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), "orange").save(source)
    project = sample_project(max_frames=1)

    manager = AnimationRenderManager()
    started = manager.submit(project=project, source_path=source)
    finished = wait_for(manager, started["id"])

    state = finished["current_frame_state"]
    assert state["frame"] == 0
    assert state["motion_applied"] is False
    assert state["cumulative_2d"]["zoom"] == pytest.approx(1.0)
    assert state["cumulative_2d"]["rotation_degrees"] == pytest.approx(0.0)
    assert state["generation"]["diffusion_mode"] == "source"
    assert state["generation"]["denoise_strength"] is None
