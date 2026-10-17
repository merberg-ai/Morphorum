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
