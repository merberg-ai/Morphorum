"""SDXL CLIP long-prompt token planning.

Pure token planning only. Conditioning remains on the existing Diffusers path
until encoder outputs, pooled embeddings, and animation interpolation are tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClipChunkPlan:
    token_count: int
    max_length: int
    chunks: tuple[tuple[int, ...], ...]

    @property
    def overflow(self) -> bool:
        return self.token_count > self.max_length


def plan_clip_chunks(tokenizer: Any, text: str, *, max_chunks: int = 16) -> ClipChunkPlan:
    """Split untruncated CLIP content IDs into BOS/content/EOS padded chunks.

    Encoder-specific tokenization is essential: SDXL's CLIP-L and CLIP-G
    tokenizers can produce different lengths for the same text.
    """
    limit = int(tokenizer.model_max_length)
    if limit < 3 or limit > 4096:
        raise ValueError(f"Unsupported CLIP maximum length: {limit}")
    if max_chunks < 1:
        raise ValueError("max_chunks must be positive")
    raw = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
    if raw and isinstance(raw[0], (list, tuple)):
        raw = raw[0]
    ids = list(map(int, raw))
    bos = int(tokenizer.bos_token_id)
    eos = int(tokenizer.eos_token_id)
    pad = int(tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos)
    capacity = limit - 2
    slices = [ids[i:i + capacity] for i in range(0, len(ids), capacity)] or [[]]
    if len(slices) > max_chunks:
        raise ValueError(
            f"SDXL prompt requires {len(slices)} CLIP chunks; maximum is {max_chunks}."
        )
    chunks = tuple(
        tuple([bos, *part, eos, *([pad] * (capacity - len(part))))
        for part in slices
    )
    return ClipChunkPlan(
        token_count=len(ids) + 2,
        max_length=limit,
        chunks=chunks,
    )
