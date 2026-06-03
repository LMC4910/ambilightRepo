"""Tests for the gradient engine (FR-GRAD-02..06)."""

import pytest

from ambilight.gradient_engine import (
    generate_gradient, rgb_to_oklab, oklab_to_rgb, _apply_gamma,
)

ZONES = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]


@pytest.mark.parametrize("mode", ["linear", "radial", "ambient", "screen_matched"])
@pytest.mark.parametrize("steps", [1, 10, 50])
def test_gradient_length(mode, steps):
    px = generate_gradient(mode, ZONES, steps)
    assert len(px) == steps
    for c in px:
        assert len(c) == 3 and all(0 <= v <= 255 for v in c)


def test_oklab_round_trip():
    for rgb in [(255, 0, 0), (0, 128, 64), (10, 200, 250), (255, 255, 255)]:
        L, a, b = rgb_to_oklab(*rgb)
        back = oklab_to_rgb(L, a, b)
        assert all(abs(x - y) <= 2 for x, y in zip(rgb, back))


def test_gamma_identity_when_one():
    px = [(10, 20, 30), (200, 100, 50)]
    assert _apply_gamma(px, 1.0) == px


def test_empty_colors_safe():
    assert generate_gradient("linear", [], 5) == [(0, 0, 0)] * 5
