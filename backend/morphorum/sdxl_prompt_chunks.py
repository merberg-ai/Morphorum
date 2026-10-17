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
        tuple([bos, *part, eos, *([pad] * (capacity - len(part)))])
        for part in slices
    )
    return ClipChunkPlan(
        token_count=len(ids) + 2,
        max_length=limit,
        chunks=chunks,
    )


def encode_sdxl_long_prompts(
    pipe: Any, prompt: str, negative_prompt: str = "",
    *, do_classifier_free_guidance: bool = True, max_chunks: int = 16,
) -> tuple[Any, Any | None, Any, Any | None]:
    """Encode both SDXL CLIP towers without silently truncating prompt content.

    Produces the same four-element layout as Diffusers SDXL encode_prompt:
    prompt embeddings, negative embeddings, positive pooled, negative pooled.
    LoRA adapter state must already be configured on the pipeline.
    """
    import torch

    towers = (
        (pipe.tokenizer, pipe.text_encoder),
        (pipe.tokenizer_2, pipe.text_encoder_2),
    )
    positive_plans = [
        plan_clip_chunks(tok, prompt, max_chunks=max_chunks) for tok, _ in towers
    ]
    negative_plans = [
        plan_clip_chunks(tok, negative_prompt, max_chunks=max_chunks)
        for tok, _ in towers
    ] if do_classifier_free_guidance else []
    chunk_count = max(
        *(len(plan.chunks) for plan in positive_plans),
        *(len(plan.chunks) for plan in negative_plans),
    )
    empty_chunks = [
        plan_clip_chunks(tok, "", max_chunks=max_chunks).chunks[0]
        for tok, _ in towers
    ]

    def encode(plans: list[ClipChunkPlan]) -> tuple[Any, Any]:
        tower_outputs = []
        pooled = None
        for tower_index, ((_, encoder), plan) in enumerate(zip(towers, plans)):
            device = next(encoder.parameters()).device
            parts = []
            for chunk_index in range(chunk_count):
                token_ids = (
                    plan.chunks[chunk_index] if chunk_index < len(plan.chunks)
                    else empty_chunks[tower_index]
                )
                ids = torch.tensor([token_ids], dtype=torch.long, device=device)
                output = encoder(ids, output_hidden_states=True)
                parts.append(output.hidden_states[-2])
                if tower_index == 1 and chunk_index == 0:
                    pooled = getattr(output, "text_embeds", None)
                    if pooled is None:
                        pooled = output[0]
            tower_outputs.append(torch.cat(parts, dim=1))
        if pooled is None:
            raise ValueError("SDXL second CLIP encoder returned no pooled conditioning.")
        return torch.cat(tower_outputs, dim=-1), pooled

    positive, positive_pooled = encode(positive_plans)
    if not do_classifier_free_guidance:
        return positive, None, positive_pooled, None
    negative, negative_pooled = encode(negative_plans)
    return positive, negative, positive_pooled, negative_pooled
