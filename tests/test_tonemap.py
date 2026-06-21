"""Tests for HDR→SDR tone-mapping (G2).

The tone-map runs on the downscaled analysis frame and must (a) be a true no-op
at neutral settings / on empty input, and (b) increase saturation and contrast
on a washed (flat, grey-ish) frame so HDR content yields vivid LED colours.
"""

import numpy as np

from ambilight.tonemap import tonemap_bgr


def _saturation(frame: np.ndarray) -> float:
    """Mean (max-min) channel spread — a cheap saturation proxy."""
    f = frame.astype(np.float32)
    return float((f.max(axis=2) - f.min(axis=2)).mean())


def test_neutral_settings_are_identity():
    frame = np.random.randint(0, 256, (45, 80, 3), dtype=np.uint8)
    out = tonemap_bgr(frame, exposure=1.0, contrast=1.0, saturation_recovery=1.0)
    assert out is frame  # returned unchanged, no copy


def test_empty_frame_is_returned_unchanged():
    empty = np.empty((0, 0, 3), np.uint8)
    assert tonemap_bgr(empty) is empty


def test_recovery_increases_saturation_on_washed_frame():
    # A washed HDR-through-SDR frame: a muted colour close to grey.
    washed = np.empty((45, 80, 3), np.uint8)
    washed[:] = (120, 130, 150)  # BGR, low spread
    out = tonemap_bgr(washed, saturation_recovery=1.8, contrast=1.0)
    assert _saturation(out) > _saturation(washed)


def test_contrast_deepens_shadows_and_lifts_highlights():
    # Mid-grey moves little; dark gets darker, bright gets brighter.
    dark = np.full((10, 10, 3), 60, np.uint8)
    bright = np.full((10, 10, 3), 200, np.uint8)
    out_dark = tonemap_bgr(dark, contrast=1.4, saturation_recovery=1.0)
    out_bright = tonemap_bgr(bright, contrast=1.4, saturation_recovery=1.0)
    assert out_dark.mean() < dark.mean()
    assert out_bright.mean() > bright.mean()


def test_output_is_uint8_and_clipped():
    frame = np.random.randint(0, 256, (20, 20, 3), dtype=np.uint8)
    out = tonemap_bgr(frame, exposure=2.0, contrast=2.0, saturation_recovery=2.0)
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255
