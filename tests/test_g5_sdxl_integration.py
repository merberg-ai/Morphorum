"""G5.1 cross-feature regression matrix: CPU-only SDXL rendering contracts.

These tests exercise the real conditioning and sampler integration points with
small synthetic CLIP towers. They do not claim GPU/image-quality acceptance.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from morphorum.animation_render import (
    MAX_CONDITIONING_CACHE_ENTRIES, _prompt_conditioning_kwargs,
)
from morphorum.generation import (
    GenerationError, GenerationJob, GenerationManager, GenerationRequest,
)
from morphorum.sdxl_prompt_chunks import (
    encode_sdxl_long_prompts, plan_clip_chunks,
)


class TinyCLIPTokenizer:
    model_max_length = 7
    bos_token_id = 101
    eos_token_id = 102
    pad_token_id = 102

    def __init__(self, repeat=1):
        self.repeat = repeat

    def __call__(self, text, *, add_special_tokens, truncation):
        assert add_special_tokens is False and truncation is False
        values = [int(word) for word in text.split()] if text else []
        return {"input_ids": [n for value in values for n in [value] * self.repeat]}


class TinyCLIPEncoder(torch.nn.Module):
    def __init__(self, width):
        super().__init__()
        self.width = width
        self.scale = torch.nn.Parameter(torch.tensor(1.0))
        self.calls = []

    def forward(self, input_ids, *, output_hidden_states=False):
        assert output_hidden_states
        self.calls.append(input_ids.detach().cpu().tolist()[0])
        hidden = input_ids.float().unsqueeze(-1).expand(-1, -1, self.width) * self.scale
        return SimpleNamespace(
            hidden_states=(hidden, torch.zeros_like(hidden)),
            text_embeds=hidden[:, 1, :],
        )


class TinySDXLPipeline:
    def __init__(self):
        self.tokenizer = TinyCLIPTokenizer()
        self.tokenizer_2 = TinyCLIPTokenizer(repeat=2)
        self.text_encoder = TinyCLIPEncoder(3)
        self.text_encoder_2 = TinyCLIPEncoder(5)
        self.standard_calls = 0

    def encode_prompt(self, *, prompt, negative_prompt,
                      num_images_per_prompt, do_classifier_free_guidance):
        self.standard_calls += 1
        # A deliberately distinct short-prompt result, so tests can observe
        # when Diffusers' original encoder is used instead of our chunker.
        sequence = torch.zeros((1, 7, 8))
        pooled = torch.zeros((1, 5))
        return (
            sequence, sequence.clone() if do_classifier_free_guidance else None,
            pooled, pooled.clone() if do_classifier_free_guidance else None,
        )


def _window(from_text, to_text, weight=0.5):
    return {
        "from_frame": 0, "to_frame": 10,
        "from_text": from_text, "to_text": to_text,
        "from_weight": 1 - weight, "to_weight": weight,
    }


def test_g51_short_sdxl_prompt_keeps_standard_diffusers_path():
    pipe = TinySDXLPipeline()
    args = {"prompt": "1 2", "negative_prompt": "3", "guidance_scale": 7.0}
    result = GenerationManager.apply_sdxl_long_prompt_conditioning(pipe, args)
    assert result is args
    assert "prompt_embeds" not in result
    assert not pipe.text_encoder.calls
    assert not pipe.text_encoder_2.calls
    assert GenerationManager.sdxl_conditioning_diagnostic(pipe, result)["mode"] == "standard"


@pytest.mark.parametrize(
    "positive,negative,expected_chunks",
    [
        ("1 2 3 4 5 6", "1", 3),        # CLIP-G positive overflows
        ("1 2", "1 2 3 4 5 6 7", 3),    # Negative-only overflow
        ("1 2 3 4 5 6 7 8", "1 2 3 4 5 6 7 8 9 10 11", 5),
    ],
)
def test_g51_txt2img_long_positive_and_negative_keep_all_tokens(
    positive, negative, expected_chunks,
):
    pipe = TinySDXLPipeline()
    args = {
        "prompt": positive, "negative_prompt": negative,
        "guidance_scale": 7.0, "num_inference_steps": 12,
    }
    result = GenerationManager.apply_sdxl_long_prompt_conditioning(pipe, args)
    assert result is not args
    assert args["prompt"] == positive
    assert result["prompt"] is None and result["negative_prompt"] is None
    assert result["num_inference_steps"] == 12
    assert tuple(result["prompt_embeds"].shape) == (1, expected_chunks * 7, 8)
    assert result["negative_prompt_embeds"].shape == result["prompt_embeds"].shape
    assert tuple(result["pooled_prompt_embeds"].shape) == (1, 5)
    assert tuple(result["negative_pooled_prompt_embeds"].shape) == (1, 5)
    assert len(pipe.text_encoder.calls) == 2 * expected_chunks
    assert len(pipe.text_encoder_2.calls) == 2 * expected_chunks
    assert not result["prompt_embeds"].requires_grad
    diag = GenerationManager.sdxl_conditioning_diagnostic(
        pipe, {**result, "prompt": positive},
    )
    assert diag["mode"] == "chunked"
    assert diag["negative_aligned"]
    assert diag["clip_g"]["tokens"] == len(positive.split()) * 2 + 2
    assert diag["shape"] == [1, expected_chunks * 7, 8]
    # Tokenizer-specific token streams must survive without silent truncation.
    assert all(int(value) in {
        token for row in pipe.text_encoder.calls for token in row
    } for value in positive.split())


def test_g51_no_cfg_long_prompt_does_not_insert_negative_embeddings():
    pipe = TinySDXLPipeline()
    result = GenerationManager.apply_sdxl_long_prompt_conditioning(pipe, {
        "prompt": "1 2 3 4 5 6", "negative_prompt": "1 2 3 4",
        "guidance_scale": 1.0,
    })
    assert result["prompt_embeds"].shape == (1, 21, 8)
    assert "negative_prompt_embeds" not in result
    assert "negative_pooled_prompt_embeds" not in result
    assert len(pipe.text_encoder.calls) == 3


def test_g51_clip_chunk_limit_rejects_oversized_input_without_truncating():
    tokenizer = TinyCLIPTokenizer(repeat=2)
    with pytest.raises(ValueError, match="maximum is 2"):
        plan_clip_chunks(tokenizer, "1 2 3 4 5 6", max_chunks=2)


def test_g51_animation_blends_mixed_length_clips_and_both_negative_towers():
    pipe = TinySDXLPipeline()
    cache = {}
    positive = _window("1 2", "3 4 5 6 7 8", 0.6)
    negative = _window("1 2", "4 5 6 7 8 9 10", 0.25)
    kwargs = dict(
        guidance_scale=7.0, conditioning_cache=cache,
        lora_signature=(("style", 0.6),),
    )
    blended = _prompt_conditioning_kwargs(
        pipe, "sdxl", positive, negative, **kwargs,
    )
    assert blended["prompt"] is None
    assert blended["negative_prompt"] is None
    assert blended["prompt_embeds"].shape == (1, 21, 8)
    assert blended["negative_prompt_embeds"].shape == (1, 21, 8)
    start = encode_sdxl_long_prompts(
        pipe, "1 2", "1 2", min_chunks=3,
    )
    end = encode_sdxl_long_prompts(
        pipe, "3 4 5 6 7 8", "4 5 6 7 8 9 10", min_chunks=3,
    )
    assert torch.allclose(
        blended["prompt_embeds"], start[0] * 0.4 + end[0] * 0.6,
    )
    assert torch.allclose(
        blended["negative_prompt_embeds"], start[1] * 0.75 + end[1] * 0.25,
    )
    assert torch.allclose(
        blended["pooled_prompt_embeds"], start[2] * 0.4 + end[2] * 0.6,
    )
    assert torch.allclose(
        blended["negative_pooled_prompt_embeds"],
        start[3] * 0.75 + end[3] * 0.25,
    )
    initial_calls = len(pipe.text_encoder.calls)
    again = _prompt_conditioning_kwargs(
        pipe, "sdxl", positive, negative, **kwargs,
    )
    assert torch.equal(blended["prompt_embeds"], again["prompt_embeds"])
    assert len(pipe.text_encoder.calls) == initial_calls
    _prompt_conditioning_kwargs(
        pipe, "sdxl", positive, negative,
        **{**kwargs, "lora_signature": (("style", 0.9),)},
    )
    assert len(pipe.text_encoder.calls) > initial_calls
    assert len(cache) <= MAX_CONDITIONING_CACHE_ENTRIES


def test_g51_long_prompt_img2img_uses_same_conditioning_contract():
    manager = GenerationManager()
    model = {"family": "sdxl"}
    request = GenerationRequest(
        model_id="sdxl-test", prompt="1 2 3 4 5 6",
        negative_prompt="1 2", width=512, height=512,
        guidance_scale=7.5,
    )
    image = object()
    args = manager.build_img2img_call_args(
        request, model, image=image, strength=0.55,
        generator="generator", on_step_end=lambda *args: None,
    )
    result = manager.apply_sdxl_long_prompt_conditioning(TinySDXLPipeline(), args)
    assert result["image"] is image
    assert result["strength"] == 0.55
    assert result["prompt"] is None
    assert result["prompt_embeds"].shape == (1, 21, 8)
    assert result["negative_prompt_embeds"].shape == (1, 21, 8)


@pytest.mark.parametrize(
    "sampler,schedule,config_key",
    [
        ("euler", "normal", None),
        ("euler", "karras", "use_karras_sigmas"),
        ("euler", "exponential", "use_exponential_sigmas"),
        ("euler", "beta", "use_beta_sigmas"),
        ("euler", "trailing", "timestep_spacing"),
        ("dpmpp_2m", "karras", "use_karras_sigmas"),
        ("dpmpp_2m_sde", "normal", None),
        ("ddim", "normal", None),
        ("heun", "trailing", "timestep_spacing"),
        ("unipc", "exponential", "use_exponential_sigmas"),
        ("dpm2", "normal", None),
        ("deis", "normal", None),
        ("dpmpp_singlestep", "normal", None),
    ],
)
def test_g51_sdxl_sampler_schedule_contract(sampler, schedule, config_key):
    from diffusers import DDIMScheduler

    manager = GenerationManager()
    pipe = SimpleNamespace(scheduler=DDIMScheduler(num_train_timesteps=1000))
    manager._configure_sampler(pipe, "sdxl", sampler, schedule)
    assert manager._pipeline_sampler == sampler
    config = pipe.scheduler.config
    if config_key == "timestep_spacing":
        assert config.timestep_spacing == "trailing"
    elif config_key:
        assert config[config_key] is True


@pytest.mark.parametrize(
    "sampler,schedule",
    [("ddim", "karras"), ("deis", "trailing"),
     ("lms", "exponential"), ("euler", "unknown")],
)
def test_g51_rejected_schedule_never_replaces_usable_scheduler(sampler, schedule):
    from diffusers import DDIMScheduler

    manager = GenerationManager()
    pipe = SimpleNamespace(scheduler=DDIMScheduler(num_train_timesteps=1000))
    original = pipe.scheduler
    with pytest.raises(GenerationError):
        manager._configure_sampler(pipe, "sdxl", sampler, schedule)
    assert pipe.scheduler is original


@pytest.mark.parametrize("family", ["flux", "zimage"])
def test_g51_non_sdxl_call_builders_never_inject_sdxl_conditioning(family):
    manager = GenerationManager()
    request = GenerationRequest(
        model_id="other-test", prompt="1 2 3", negative_prompt="4 5",
        width=512, height=512,
    )
    model = {"family": family}
    job = GenerationJob(id="test", request=request, model=model)
    image_args = manager._build_call_args(job, "generator", lambda *args: None)
    motion_args = manager.build_img2img_call_args(
        request, model, image="image", strength=0.4,
        generator="generator", on_step_end=lambda *args: None,
    )
    for args in (image_args, motion_args):
        assert args["prompt"] == request.prompt
        assert "prompt_embeds" not in args
        assert "negative_prompt_embeds" not in args
        assert "negative_prompt" not in args


def test_g52_repeated_static_long_sdxl_animation_prompt_reuses_clip_embeddings():
    pipe = TinySDXLPipeline()
    cache = {}
    stats = {"hits": 0, "misses": 0}
    positive = _window("1 2 3 4 5 6", "1 2 3 4 5 6")
    negative = _window("8 9 10", "8 9 10")
    kwargs = dict(
        guidance_scale=7.0, conditioning_cache=cache,
        cache_stats=stats, lora_signature=(("style", 0.55),),
    )
    with torch.enable_grad():
        first = _prompt_conditioning_kwargs(pipe, "sdxl", positive, negative, **kwargs)
        calls = len(pipe.text_encoder.calls) + len(pipe.text_encoder_2.calls)
        assert calls == 12  # Three chunks per tower for positive and negative.
        assert first["prompt"] is None
        assert first["prompt_embeds"].shape == (1, 21, 8)
        assert first["negative_prompt_embeds"].shape == first["prompt_embeds"].shape
        assert not first["prompt_embeds"].requires_grad
        for _ in range(30):
            second = _prompt_conditioning_kwargs(pipe, "sdxl", positive, negative, **kwargs)
            assert second["prompt_embeds"] is first["prompt_embeds"]
            assert second["negative_prompt_embeds"] is first["negative_prompt_embeds"]
        assert len(pipe.text_encoder.calls) + len(pipe.text_encoder_2.calls) == calls
    assert stats == {"hits": 30, "misses": 1}
    assert len(cache) == 1


def test_g52_static_long_sdxl_cache_invalidates_when_lora_strength_changes():
    pipe = TinySDXLPipeline()
    cache = {}
    stats = {"hits": 0, "misses": 0}
    positive = _window("1 2 3 4 5 6", "1 2 3 4 5 6")
    for frame in range(12):
        kwargs = dict(
            guidance_scale=7.0, conditioning_cache=cache,
            cache_stats=stats, lora_signature=(("style", frame / 10),),
        )
        result = _prompt_conditioning_kwargs(pipe, "sdxl", positive, {}, **kwargs)
        assert result["prompt_embeds"].shape == (1, 21, 8)
        assert len(cache) <= MAX_CONDITIONING_CACHE_ENTRIES
    assert stats == {"hits": 0, "misses": 12}
    assert len(cache) == MAX_CONDITIONING_CACHE_ENTRIES
    repeated = _prompt_conditioning_kwargs(
        pipe, "sdxl", positive, {},
        guidance_scale=7.0, conditioning_cache=cache,
        cache_stats=stats, lora_signature=(("style", 11 / 10),),
    )
    assert repeated["prompt_embeds"].shape == (1, 21, 8)
    assert stats["hits"] == 1


def test_g52_static_long_sdxl_uses_shared_blend_cache_when_keys_match():
    pipe = TinySDXLPipeline()
    cache = {}
    positive = _window("1 2 3 4 5 6", "1 2 3 4 5 6")
    static = _prompt_conditioning_kwargs(
        pipe, "sdxl", positive, _window("2", "2"), guidance_scale=7.0,
        conditioning_cache=cache, lora_signature=(("style", 0.5),),
    )
    initial = len(pipe.text_encoder.calls)
    assert list(cache) == [("sdxl", "1 2 3 4 5 6", "2", True, (("style", 0.5),), 3)]
    blended = _prompt_conditioning_kwargs(
        pipe, "sdxl",
        _window("1 2 3 4 5 6", "1 2", 0.5),
        _window("2", "3", 0.5),
        guidance_scale=7.0, conditioning_cache=cache,
        lora_signature=(("style", 0.5),),
    )
    assert blended["prompt_embeds"].shape == static["prompt_embeds"].shape
    # The initial long prompt is identical and should be recovered from cache;
    # only the second blending endpoint requires new CLIP inference.
    # One new endpoint requires three positive AND three negative CLIP passes.
    assert len(pipe.text_encoder.calls) == initial + 6


def test_g52_static_short_sdxl_keeps_native_prompt_without_using_cache():
    pipe = TinySDXLPipeline()
    cache = {}
    stats = {"hits": 0, "misses": 0}
    result = _prompt_conditioning_kwargs(
        pipe, "sdxl", _window("1 2", "1 2"), {},
        guidance_scale=7.0, conditioning_cache=cache, cache_stats=stats,
    )
    assert result == {"prompt": "1 2", "negative_prompt": None}
    assert len(cache) == 0
    assert stats == {"hits": 0, "misses": 0}
