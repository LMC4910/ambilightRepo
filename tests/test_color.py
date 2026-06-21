"""Tests for the colour-analysis strategies (FR-CLR-01..04)."""

import numpy as np
import pytest

from ambilight.color import ColorAnalyzer

MODES = ["average", "edges", "dominant", "kmeans", "saturation_weighted"]


def _solid(bgr):
    """A 16×16 region filled with a single BGR colour."""
    region = np.zeros((16, 16, 3), dtype=np.uint8)
    region[:, :] = bgr
    return region


@pytest.mark.parametrize("mode", MODES)
def test_modes_return_valid_rgb(mode):
    region = _solid((0, 0, 255))  # BGR red
    r, g, b = ColorAnalyzer(mode).analyze(region)
    for v in (r, g, b):
        assert 0 <= v <= 255


@pytest.mark.parametrize("mode", MODES)
def test_red_region_is_red_dominant(mode):
    # BGR red → RGB red; red channel should dominate for every mode.
    r, g, b = ColorAnalyzer(mode).analyze(_solid((0, 0, 255)))
    assert r > g and r > b


def test_empty_region_is_black():
    assert ColorAnalyzer("average").analyze(np.zeros((0, 0, 3), dtype=np.uint8)) == (0, 0, 0)


def test_black_pixels_ignored_for_saturation_weighted():
    # Half black, half red — black should be filtered, leaving red.
    region = np.zeros((16, 16, 3), dtype=np.uint8)
    region[:, 8:] = (0, 0, 255)  # right half BGR red
    r, g, b = ColorAnalyzer("saturation_weighted").analyze(region)
    assert r > g and r > b


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        ColorAnalyzer("not_a_mode")


def _spread(rgb):
    """Chroma proxy: max-min channel spread."""
    return max(rgb) - min(rgb)


def test_vibrance_default_is_identity():
    # A muted (low-chroma) colour must come back unchanged at vibrance 1.0.
    region = _solid((90, 110, 140))  # BGR, low spread
    base = ColorAnalyzer("average", vibrance=1.0).analyze(region)
    plain = ColorAnalyzer("average").analyze(region)
    assert base == plain


def test_vibrance_increases_chroma_without_overflow():
    region = _solid((90, 110, 140))
    base = ColorAnalyzer("average", vibrance=1.0).analyze(region)
    boosted = ColorAnalyzer("average", vibrance=1.6).analyze(region)
    assert _spread(boosted) > _spread(base)
    for v in boosted:
        assert 0 <= v <= 255  # clipped, no wraparound


def test_vibrance_preserves_grey():
    # Pure grey has no chroma to boost — stays grey.
    region = _solid((128, 128, 128))
    r, g, b = ColorAnalyzer("average", vibrance=2.0).analyze(region)
    assert r == g == b


def test_combine_zone_colors_prefers_saturated():
    analyzer = ColorAnalyzer("average")
    zone_colors = [(object(), (10, 10, 10)), (object(), (255, 0, 0))]
    r, g, b = analyzer.combine_zone_colors(zone_colors)
    assert r > g and r > b  # vivid red dominates the grey
