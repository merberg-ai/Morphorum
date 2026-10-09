from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from morphorum.animation_temporal import blend_future_anchor


def _image(color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (4, 4), color)


def test_temporal_tween_agreeing_pixels_blends_but_not_on_endpoints() -> None:
    forward = _image((100, 100, 100))
    future = _image((120, 120, 120))
    visible = Image.new("L", (4, 4), 0)
    mid = blend_future_anchor(
        forward, future, future_holes=visible,
        forward_holes=None, position=0.5, mix=1,
    )
    pixels = np.asarray(mid.image)
    assert 100 < pixels[0, 0, 0] < 120
    assert mid.fraction_blended == pytest.approx(1)
    start = blend_future_anchor(
        forward, future, future_holes=visible,
        forward_holes=None, position=0, mix=1,
    )
    assert np.array_equal(np.asarray(start.image), np.asarray(forward))


def test_temporal_tween_gates_disagreement_and_future_disocclusion() -> None:
    forward = _image((255, 0, 0))
    future = _image((0, 0, 255))
    future_mask = Image.new("L", (4, 4), 0)
    future_mask.putpixel((0, 0), 255)
    result = blend_future_anchor(
        forward, future, future_holes=future_mask,
        forward_holes=None, position=0.75, mix=1, contrast_threshold=30,
    )
    # Strong color disagreement suppresses a ghosted red/blue double exposure.
    assert np.array_equal(np.asarray(result.image), np.asarray(forward))
    assert result.fraction_blended == 0


def test_temporal_tween_can_fill_exposed_forward_pixel_from_visible_future() -> None:
    forward = _image((255, 0, 0))
    future = _image((0, 0, 255))
    future_mask = Image.new("L", (4, 4), 0)
    forward_mask = Image.new("L", (4, 4), 0)
    forward_mask.putpixel((1, 1), 255)
    result = blend_future_anchor(
        forward, future, future_holes=future_mask,
        forward_holes=forward_mask, position=0.5, mix=0.5,
        contrast_threshold=1,
    )
    output = np.asarray(result.image)
    assert result.fraction_replaced == pytest.approx(1 / 16)
    assert output[1, 1, 2] > 0
    assert output[0, 0].tolist() == [255, 0, 0]


def test_temporal_tween_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="identical dimensions"):
        blend_future_anchor(
            _image((0, 0, 0)), _image((10, 10, 10)),
            future_holes=Image.new("L", (3, 4), 0),
            forward_holes=None, position=0.5, mix=1,
        )
