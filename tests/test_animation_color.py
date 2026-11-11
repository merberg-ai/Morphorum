"""Color coherence: deterministic histogram matching back to a reference frame."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from morphorum.animation_color import (
    ColorCoherenceError,
    _lab_to_rgb,
    _rgb_to_lab,
    apply_color_coherence,
    build_color_reference,
    normalize_color_settings,
)
from morphorum.animation_projects import normalize_animation_project


def _scene(seed: int = 3, size: int = 96) -> Image.Image:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    base = np.stack([x * 2.2, y * 1.6 + 30, (x + y) * 0.9 + 20], axis=-1)
    return Image.fromarray(
        np.clip(base + rng.normal(0, 12, base.shape), 0, 255).astype(np.uint8), mode="RGB",
    )


def _drift(image: Image.Image) -> Image.Image:
    """A warm tint plus a contrast loss, like accumulated feedback drift."""
    pixels = np.asarray(image, dtype=np.float64)
    shifted = (pixels - 128) * 0.8 + 128 + np.array([24.0, 4.0, -18.0])
    return Image.fromarray(np.clip(shifted, 0, 255).astype(np.uint8), mode="RGB")


def _stats(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    pixels = np.asarray(image, dtype=np.float64).reshape(-1, 3)
    return pixels.mean(axis=0), pixels.std(axis=0)


def test_lab_conversion_round_trips_every_part_of_the_gamut():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 256, size=(4096, 3)).astype(np.float64)
    rgb[:4] = [[0, 0, 0], [255, 255, 255], [255, 0, 0], [0, 0, 255]]
    assert np.abs(_lab_to_rgb(_rgb_to_lab(rgb)) - rgb).max() < 1e-6
    white = _rgb_to_lab(np.array([[255.0, 255.0, 255.0]]))[0]
    assert white == pytest.approx([100.0, 0.0, 0.0], abs=1e-3)


@pytest.mark.parametrize("mode", ["lab", "rgb"])
def test_matching_an_image_to_itself_changes_almost_nothing(mode):
    scene = _scene()
    matched = apply_color_coherence(scene, build_color_reference(scene, mode))
    difference = np.abs(
        np.asarray(matched, dtype=np.int16) - np.asarray(scene, dtype=np.int16)
    )
    assert difference.max() <= 2
    assert difference.mean() < 0.6


@pytest.mark.parametrize("mode", ["lab", "rgb"])
def test_drifted_frame_is_pulled_back_to_reference_colors(mode):
    scene = _scene()
    drifted = _drift(scene)
    reference_mean, reference_std = _stats(scene)
    drift_mean, _ = _stats(drifted)
    assert np.abs(drift_mean - reference_mean).max() > 10

    matched = apply_color_coherence(drifted, build_color_reference(scene, mode))
    mean, std = _stats(matched)
    assert np.abs(mean - reference_mean).max() < 2.5
    assert np.abs(std - reference_std).max() < 3.0
    # Deterministic: same input, same output.
    again = apply_color_coherence(drifted, build_color_reference(scene, mode))
    assert np.array_equal(np.asarray(matched), np.asarray(again))


def test_amount_blends_between_untouched_and_fully_matched():
    scene, drifted = _scene(), _drift(_scene())
    reference = build_color_reference(scene, "lab")
    assert apply_color_coherence(drifted, reference, amount=0) is drifted
    full = np.asarray(apply_color_coherence(drifted, reference, amount=1), dtype=np.float64)
    half = np.asarray(apply_color_coherence(drifted, reference, amount=0.5), dtype=np.float64)
    expected = (np.asarray(drifted, dtype=np.float64) + full) / 2
    assert np.abs(half - expected).max() <= 1.0
    with pytest.raises(ColorCoherenceError):
        apply_color_coherence(drifted, reference, amount=1.5)
    with pytest.raises(ColorCoherenceError):
        build_color_reference(scene, "hsv")


def test_flat_images_do_not_break_matching():
    flat = Image.new("RGB", (32, 32), (40, 90, 200))
    reference = build_color_reference(flat, "lab")
    matched = apply_color_coherence(Image.new("RGB", (32, 32), (200, 60, 20)), reference)
    assert np.abs(np.asarray(matched, dtype=np.int16) - [40, 90, 200]).max() <= 2


def test_settings_are_normalized_and_default_to_off():
    assert normalize_color_settings(None) == {"coherence": "none", "amount": 1.0}
    assert normalize_color_settings({"coherence": " LAB ", "amount": "0.4"}) == {
        "coherence": "lab", "amount": 0.4,
    }
    assert normalize_color_settings({"coherence": "hsv", "amount": 7}) == {
        "coherence": "none", "amount": 1.0,
    }
    assert normalize_color_settings({"amount": float("nan")})["amount"] == 1.0
    assert normalize_color_settings({"amount": -3})["amount"] == 0.0


def test_projects_persist_color_settings_and_old_projects_stay_off():
    fresh = normalize_animation_project({"name": "Color test"})
    assert fresh["color"] == {"coherence": "none", "amount": 1.0}

    legacy = dict(fresh)
    legacy.pop("color")
    assert normalize_animation_project(legacy, existing=legacy)["color"]["coherence"] == "none"

    saved = normalize_animation_project(
        {**fresh, "color": {"coherence": "lab", "amount": 0.75}}, existing=fresh,
    )
    assert saved["color"] == {"coherence": "lab", "amount": 0.75}
