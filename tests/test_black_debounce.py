"""Tests for the transient-black debounce that stops the strip blinking off on
a static screen when the capture backend emits a lone black frame."""

import numpy as np

from ambilight.config import AppConfig
from ambilight.pipeline import AmbilightPipeline, _Channel, _BLACK_DEBOUNCE_FRAMES


def _frame(value):
    return np.full((45, 80, 3), value, dtype=np.uint8)


BLACK = _frame(0)
BRIGHT = _frame(200)


def _channel():
    # Only black_streak is exercised by _hold_transient_black; the rest are unused.
    return _Channel(name="d", monitor_index=0, led=None, zones=None,
                    analyzer=None, smoother=None, led_count=30)


def _pipeline():
    return AmbilightPipeline(config=AppConfig())


def test_lone_black_frame_is_held():
    p, ch = _pipeline(), _channel()
    assert p._hold_transient_black(ch, BRIGHT) is False     # normal frame
    assert p._hold_transient_black(ch, BLACK) is True        # 1st black → hold


def test_black_within_window_held_then_released():
    p, ch = _pipeline(), _channel()
    # The first _BLACK_DEBOUNCE_FRAMES black frames are held...
    for _ in range(_BLACK_DEBOUNCE_FRAMES):
        assert p._hold_transient_black(ch, BLACK) is True
    # ...the next one is a sustained black-out → let it through.
    assert p._hold_transient_black(ch, BLACK) is False


def test_non_black_resets_streak():
    p, ch = _pipeline(), _channel()
    for _ in range(_BLACK_DEBOUNCE_FRAMES):
        p._hold_transient_black(ch, BLACK)
    p._hold_transient_black(ch, BRIGHT)          # reset
    assert ch.black_streak == 0
    assert p._hold_transient_black(ch, BLACK) is True   # debounce starts over


def test_alternating_black_never_releases():
    # WGC delivering black every other frame must not blink: each black frame is
    # held because the streak never exceeds the window.
    p, ch = _pipeline(), _channel()
    for _ in range(20):
        assert p._hold_transient_black(ch, BLACK) is True   # streak == 1, held
        assert p._hold_transient_black(ch, BRIGHT) is False  # resets streak
