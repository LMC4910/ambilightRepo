"""Tests for the adaptive EMA smoothing engine (FR-CLR-05)."""

from ambilight.smoothing import SmoothingEngine


def _engine(**kw):
    defaults = dict(enabled=True, base_alpha=0.15, fast_alpha=0.55, fast_threshold=60, min_change=2)
    defaults.update(kw)
    return SmoothingEngine(**defaults)


def test_disabled_passes_through():
    eng = _engine(enabled=False)
    assert eng.smooth_combined((123, 45, 200)) == (123, 45, 200)


def test_ema_converges_toward_target():
    eng = _engine()
    last = eng.smooth_combined((0, 0, 0))
    target = (255, 255, 255)
    for _ in range(200):
        last = eng.smooth_combined(target)
    assert all(c >= 250 for c in last)  # converges near white


def test_min_change_dead_zone():
    # A sub-threshold change from the established value should not move output.
    eng = _engine(min_change=10)
    eng.smooth_combined((100, 100, 100))
    out = eng.smooth_combined((103, 100, 100))  # delta 3 < min_change 10
    assert out == (100, 100, 100)


def test_fast_alpha_moves_more_than_base():
    big = _engine()
    small = _engine()
    big.smooth_combined((0, 0, 0))
    small.smooth_combined((0, 0, 0))
    # Large jump (>= fast_threshold) should use fast alpha → larger first step
    big_step = big.smooth_combined((255, 255, 255))[0]
    # Small jump (< fast_threshold) → base alpha → smaller step
    small.smooth_combined((0, 0, 0))
    small_step = small.smooth_combined((40, 40, 40))[0]
    assert big_step > small_step
