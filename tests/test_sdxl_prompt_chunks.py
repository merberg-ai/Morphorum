from __future__ import annotations

import pytest

from morphorum.sdxl_prompt_chunks import plan_clip_chunks


class Tokenizer:
    model_max_length = 7
    bos_token_id = 101
    eos_token_id = 102
    pad_token_id = 102

    def __call__(self, text, **kwargs):
        assert kwargs == {"add_special_tokens": False, "truncation": False}
        return {"input_ids": [int(x) for x in text.split()] if text else []}


def test_clip_chunks_preserve_all_tokens_without_truncation():
    plan = plan_clip_chunks(Tokenizer(), "1 2 3 4 5 6 7 8")
    assert plan.token_count == 10
    assert plan.overflow
    assert plan.chunks == (
        (101, 1, 2, 3, 4, 5, 102),
        (101, 6, 7, 8, 102, 102, 102),
    )


def test_empty_and_short_prompts_have_single_padded_chunk():
    assert plan_clip_chunks(Tokenizer(), "").chunks == (
        (101, 102, 102, 102, 102, 102, 102),
    )
    assert not plan_clip_chunks(Tokenizer(), "1 2").overflow


def test_max_chunks_prevents_unbounded_conditioning_length():
    with pytest.raises(ValueError, match="maximum is 1"):
        plan_clip_chunks(Tokenizer(), "1 2 3 4 5 6", max_chunks=1)


def test_dual_clip_long_encoding_shapes_and_pooled_outputs():
    import torch
    from types import SimpleNamespace
    from morphorum.sdxl_prompt_chunks import encode_sdxl_long_prompts

    class Encoder:
        def __init__(self, width):
            self.width = width

        def parameters(self):
            yield torch.zeros(1)

        def __call__(self, ids, output_hidden_states=False):
            assert output_hidden_states
            sequence = ids.shape[1]
            hidden = torch.ones((1, sequence, self.width))
            return SimpleNamespace(
                hidden_states=(hidden, hidden * 0),
                text_embeds=torch.ones((1, self.width)) * 2,
            )

    pipe = SimpleNamespace(
        tokenizer=Tokenizer(), tokenizer_2=Tokenizer(),
        text_encoder=Encoder(3), text_encoder_2=Encoder(5),
    )
    positive, negative, pooled, negative_pooled = encode_sdxl_long_prompts(
        pipe, "1 2 3 4 5 6 7 8", "1 2",
    )
    assert tuple(positive.shape) == (1, 14, 8)
    assert tuple(negative.shape) == (1, 14, 8)
    assert tuple(pooled.shape) == (1, 5)
    assert tuple(negative_pooled.shape) == (1, 5)
    assert torch.all(positive == 1)
    no_cfg = encode_sdxl_long_prompts(
        pipe, "1 2", do_classifier_free_guidance=False,
    )
    assert no_cfg[1] is None and no_cfg[3] is None


def test_long_sdxl_encoder_can_pad_to_transition_endpoint_length():
    import torch
    from types import SimpleNamespace
    from morphorum.sdxl_prompt_chunks import encode_sdxl_long_prompts

    class Encoder:
        def __init__(self, size):
            self.size = size

        def parameters(self):
            yield torch.zeros(1)

        def __call__(self, ids, output_hidden_states=False):
            hidden = torch.ones(1, ids.shape[1], self.size)
            return SimpleNamespace(
                hidden_states=(hidden, hidden),
                text_embeds=torch.ones(1, self.size),
            )

    pipe = SimpleNamespace(
        tokenizer=Tokenizer(), tokenizer_2=Tokenizer(),
        text_encoder=Encoder(3), text_encoder_2=Encoder(5),
    )
    a = encode_sdxl_long_prompts(pipe, "1 2", min_chunks=3)
    b = encode_sdxl_long_prompts(pipe, "1 2 3 4 5 6 7 8 9 10 11")
    assert a[0].shape == b[0].shape == (1, 21, 8)
    assert a[1].shape == b[1].shape == (1, 21, 8)
