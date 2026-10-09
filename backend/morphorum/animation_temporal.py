from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TemporalBlendResult:
    image: Image.Image
    fraction_blended: float
    fraction_replaced: float
    average_weight: float


def blend_future_anchor(
    forward: Image.Image,
    reprojected_future: Image.Image,
    *,
    future_holes: Image.Image,
    forward_holes: Image.Image | None,
    position: float,
    mix: float,
    contrast_threshold: float = 96.0,
) -> TemporalBlendResult:
    """Confidence-gated two-anchor blend, with an exposed-pixel repair path.

    Only pixels supported by future-anchor geometry can be borrowed. Regions
    where both frames have visible content are blended conservatively if they
    agree in RGB appearance; wildly different hallucinated objects must not
    produce double-exposure ghosts. Disoccluded pixels in the forward render
    can borrow future content regardless of disagreement.
    """
    a = np.asarray(forward.convert("RGB"), dtype=np.float32)
    b = np.asarray(reprojected_future.convert("RGB"), dtype=np.float32)
    holes = np.asarray(future_holes.convert("L"), dtype=np.uint8)
    if a.shape != b.shape or holes.shape != a.shape[:2]:
        raise ValueError("Temporal blend images and future mask must have identical dimensions.")
    if forward_holes is None:
        uncovered_forward = np.zeros(a.shape[:2], dtype=bool)
    else:
        previous_mask = np.asarray(forward_holes.convert("L"), dtype=np.uint8)
        if previous_mask.shape != a.shape[:2]:
            raise ValueError("Temporal blend forward mask must match image dimensions.")
        uncovered_forward = previous_mask > 0

    position = max(0.0, min(1.0, float(position)))
    mix = max(0.0, min(1.0, float(mix)))
    if not np.isfinite(position) or not np.isfinite(mix):
        raise ValueError("Temporal blend position and mix must be finite.")
    if not np.isfinite(contrast_threshold) or contrast_threshold <= 0:
        raise ValueError("Temporal contrast threshold must be positive and finite.")

    supported = holes == 0
    discrepancy = np.mean(np.abs(a - b), axis=2)
    confidence = np.clip(1.0 - discrepancy / float(contrast_threshold), 0.0, 1.0)
    base_weight = position * mix
    weights = base_weight * confidence
    replacement = supported & uncovered_forward
    weights[replacement] = max(base_weight, 0.5 * position)
    weights[~supported] = 0.0
    mixed = np.clip(np.rint(
        a * (1.0 - weights[..., None]) + b * weights[..., None]
    ), 0, 255).astype(np.uint8)
    return TemporalBlendResult(
        image=Image.fromarray(mixed, mode="RGB"),
        fraction_blended=float(np.count_nonzero(weights > 1e-5) / weights.size),
        fraction_replaced=float(np.count_nonzero(replacement) / weights.size),
        average_weight=float(weights.mean()),
    )
