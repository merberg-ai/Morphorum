"""Color coherence for feedback animation renders.

Every rendered frame is warped, re-encoded and re-diffused from the previous
one, so small color and contrast shifts compound over a long render. Matching
each diffusion input back to the color distribution of the first frame keeps
that drift bounded. This is a deterministic CPU histogram match; it never
changes geometry and never touches saved frames directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image

COLOR_COHERENCE_MODES = ("none", "lab", "rgb")
DEFAULT_COLOR_SETTINGS = {"coherence": "none", "amount": 1.0}

# Fixed channel ranges and bin counts keep the match deterministic.
_RANGES = {
    "rgb": ((-0.5, 255.5, 256),) * 3,  # one bin per 8-bit level
    "lab": ((0.0, 100.0, 1024), (-128.0, 128.0, 1024), (-128.0, 128.0, 1024)),
}
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float64)
_XYZ_TO_RGB = np.linalg.inv(_RGB_TO_XYZ)
_EPSILON = 216.0 / 24389.0
_KAPPA = 24389.0 / 27.0


class ColorCoherenceError(ValueError):
    """Invalid color coherence configuration or reference."""


def normalize_color_settings(value: Any) -> dict[str, Any]:
    """Coerce a project's color section; unknown modes fall back to off."""
    source = value if isinstance(value, dict) else {}
    mode = str(source.get("coherence") or "none").strip().lower()
    if mode not in COLOR_COHERENCE_MODES:
        mode = "none"
    try:
        amount = float(source.get("amount", 1.0))
    except (TypeError, ValueError, OverflowError):
        amount = 1.0
    if not np.isfinite(amount):
        amount = 1.0
    return {"coherence": mode, "amount": float(min(1.0, max(0.0, amount)))}


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    linear = rgb / 255.0
    linear = np.where(
        linear <= 0.04045, linear / 12.92, ((linear + 0.055) / 1.055) ** 2.4,
    )
    xyz = (linear @ _RGB_TO_XYZ.T) / _WHITE_D65
    f = np.where(xyz > _EPSILON, np.cbrt(xyz), (_KAPPA * xyz + 16.0) / 116.0)
    return np.stack(
        [116.0 * f[..., 1] - 16.0,
         500.0 * (f[..., 0] - f[..., 1]),
         200.0 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    cubed = f ** 3
    xyz = np.where(cubed > _EPSILON, cubed, (116.0 * f - 16.0) / _KAPPA) * _WHITE_D65
    linear = np.clip(xyz @ _XYZ_TO_RGB.T, 0.0, 1.0)
    encoded = np.where(
        linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1.0 / 2.4) - 0.055,
    )
    return encoded * 255.0


def _to_space(image: Image.Image, mode: str) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    return _rgb_to_lab(rgb) if mode == "lab" else rgb


def _bin_index(values: np.ndarray, low: float, high: float, bins: int) -> np.ndarray:
    return np.clip(
        np.floor((values - low) * (bins / (high - low))), 0, bins - 1,
    ).astype(np.int64)


@dataclass(frozen=True)
class ColorReference:
    """Per-channel cumulative histograms of the reference frame."""
    mode: str
    cumulative: tuple[np.ndarray, np.ndarray, np.ndarray]


def build_color_reference(image: Image.Image, mode: str) -> ColorReference:
    if mode not in _RANGES:
        raise ColorCoherenceError("Color coherence mode must be LAB or RGB.")
    pixels = _to_space(image, mode).reshape(-1, 3)
    if not pixels.size:
        raise ColorCoherenceError("Color reference image is empty.")
    cumulative = []
    for channel, (low, high, bins) in enumerate(_RANGES[mode]):
        counts = np.bincount(_bin_index(pixels[:, channel], low, high, bins), minlength=bins)
        cumulative.append(np.cumsum(counts) / pixels.shape[0])
    return ColorReference(mode=mode, cumulative=tuple(cumulative))


def apply_color_coherence(
    image: Image.Image, reference: ColorReference, *, amount: float = 1.0,
) -> Image.Image:
    """Histogram-match ``image`` to the reference, blended by ``amount``."""
    amount = float(amount)
    if not 0.0 <= amount <= 1.0:
        raise ColorCoherenceError("Color coherence amount must be between 0 and 1.")
    if amount <= 0.0:
        return image
    original = np.asarray(image.convert("RGB"), dtype=np.float64)
    working = _rgb_to_lab(original) if reference.mode == "lab" else original.copy()
    for channel, (low, high, bins) in enumerate(_RANGES[reference.mode]):
        values = working[..., channel]
        index = _bin_index(values, low, high, bins)
        counts = np.bincount(index.ravel(), minlength=bins)
        # Classic discrete histogram matching: each source bin takes its
        # mid-rank and moves to the reference bin holding that rank. Ranks are
        # never interpolated, so sparse tails and the gaps 8-bit images leave
        # between occupied bins cannot land a pixel on a far-away color, and
        # matching an image to itself is exactly the identity.
        probability = (np.cumsum(counts) - counts / 2.0) / index.size
        target = np.clip(
            np.searchsorted(reference.cumulative[channel], probability, side="left"),
            0, bins - 1,
        )
        # Shift by whole bins so detail finer than one bin is kept.
        working[..., channel] = values + (target - np.arange(bins))[index] * ((high - low) / bins)
    matched = _lab_to_rgb(working) if reference.mode == "lab" else working
    blended = original + (matched - original) * amount
    return Image.fromarray(np.clip(np.rint(blended), 0, 255).astype(np.uint8), mode="RGB")
