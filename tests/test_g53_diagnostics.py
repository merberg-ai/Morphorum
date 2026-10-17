"""G5.3 diagnostics contracts, independent of GPU and diffusion model downloads."""
from __future__ import annotations

import torch

from morphorum.generation import GenerationManager, GenerationRequest


class Tokenizer:
    model_max_length = 7
    bos_token_id = 1
    eos_token_id = 2
    pad_token_id = 2

    def __call__(self, text, *, truncation=False, add_special_tokens=True):
        assert truncation is False
        ids = list(range(len(text.split())))
        if add_special_tokens:
            ids = [self.bos_token_id, *ids, self.eos_token_id]
        return {"input_ids": ids}


class Pipeline:
    tokenizer = Tokenizer()
    tokenizer_2 = Tokenizer()
    text_encoder = object()
    text_encoder_2 = object()


def test_g53_expected_sdxl_long_prompt_is_info_not_truncation_warning(monkeypatch):
    import morphorum.generation as generation

    events = []
    monkeypatch.setattr(
        generation, "emit_console",
        lambda level, source, message: events.append((level, source, message)),
    )
    request = GenerationRequest(
        model_id="sdxl", prompt="one two three four five six",
        negative_prompt="bad pixels", guidance_scale=7.0,
    )
    assert GenerationManager._warn_sdxl_prompt_truncation(Pipeline(), request) == []
    assert len(events) == 1
    assert events[0][0] == "info"
    assert "Chunked conditioning" in events[0][2]
    assert "CLIP-L" in events[0][2] and "CLIP-G" in events[0][2]


def test_g53_missing_sdxl_encoder_keeps_genuine_overflow_warning(monkeypatch):
    import morphorum.generation as generation

    events = []
    monkeypatch.setattr(
        generation, "emit_console",
        lambda level, source, message: events.append((level, message)),
    )

    class MissingEncoder:
        tokenizer = Tokenizer()
        tokenizer_2 = Tokenizer()
        text_encoder = None
        text_encoder_2 = object()

    warnings = GenerationManager._warn_sdxl_prompt_truncation(
        MissingEncoder(),
        GenerationRequest(model_id="sdxl", prompt="1 2 3 4 5 6"),
    )
    assert len(warnings) == 1
    assert "may be truncated" in warnings[0]
    assert events == [("warning", warnings[0])]


def test_g53_sdxl_diagnostic_counts_positive_and_negative_separately():
    pipe = Pipeline()
    tensor = torch.zeros((1, 14, 8))
    report = GenerationManager.sdxl_conditioning_diagnostic(pipe, {
        "prompt": "1 2 3 4 5 6",
        "negative_prompt": "9 8 7",
        "guidance_scale": 7.0,
        "prompt_embeds": tensor,
        "negative_prompt_embeds": tensor.clone(),
    })
    assert report["mode"] == "chunked"
    assert report["shape"] == [1, 14, 8]
    assert report["negative_aligned"]
    assert report["clip_l"]["tokens"] == 8
    assert report["clip_g"]["chunks"] == 2
    assert report["clip_l_negative"]["tokens"] == 5
    assert report["clip_g_negative"]["chunks"] == 1


def test_g53_sdxl_no_guidance_does_not_claim_negative_embedding_alignment():
    report = GenerationManager.sdxl_conditioning_diagnostic(Pipeline(), {
        "prompt": "1",
        "negative_prompt": "",
        "guidance_scale": 1.0,
        "prompt_embeds": torch.zeros((1, 7, 8)),
    })
    assert report["mode"] == "embedded"
    assert report["guidance_active"] is False
    assert report["negative_aligned"] is None
