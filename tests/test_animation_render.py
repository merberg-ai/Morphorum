from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import torch
from PIL import Image

import morphorum.animation_render as animation_render
from morphorum.animation_render import (
    AnimationRenderManager,
    _prompt_conditioning_kwargs,
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
            "strength": "0:(0)",
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


def test_strength_zero_render_persists_frames_manifest_and_preview(
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
