"""Tests for effects, scheduler window parsing, and the registry (FR-EFF-03..08)."""

import datetime

from ambilight.effects_engine import (
    EffectsManager, EffectScheduler, CandleEffect,
    SunriseEffect, SunsetEffect, OceanEffect, AmbientEffect,
    _parse_window, _in_window, _gradient_at,
)


def test_parse_window():
    assert _parse_window("22:00-07:00") == (22 * 60, 7 * 60)
    assert _parse_window("09:30-17:45") == (9 * 60 + 30, 17 * 60 + 45)


def test_in_window_same_day():
    start, end = _parse_window("09:00-17:00")
    assert _in_window(12 * 60, start, end)
    assert not _in_window(8 * 60, start, end)


def test_in_window_overnight_wrap():
    start, end = _parse_window("22:00-07:00")
    assert _in_window(23 * 60, start, end)      # late night
    assert _in_window(6 * 60, start, end)       # early morning
    assert not _in_window(12 * 60, start, end)  # midday


def test_scheduler_current():
    s = EffectScheduler([{"effect": "candle", "params": {}, "window": "22:00-07:00"}])
    assert s.current(datetime.datetime(2026, 1, 1, 23, 30)) is not None
    assert s.current(datetime.datetime(2026, 1, 1, 12, 0)) is None


def test_manager_registry_and_bogus_mode():
    m = EffectsManager()
    effects = m.list_effects()
    for name in ("screen_sync", "static", "breathing", "rainbow", "candle"):
        assert name in effects
    assert m.set_mode("candle", {"speed": 1.0}) is True
    assert m.set_mode("does_not_exist") is False


def test_candle_in_range():
    c = CandleEffect(255, 140, 40)
    for _ in range(50):
        r, g, b = c.update()
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255


def test_scene_presets_registered():
    effects = EffectsManager().list_effects()
    for name in ("sunrise", "sunset", "ocean", "ambient", "audio"):
        assert name in effects


def test_gradient_at_clamps_endpoints():
    keys = [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))]
    assert _gradient_at(keys, -1.0) == (0, 0, 0)     # clamps low
    assert _gradient_at(keys, 2.0) == (255, 255, 255)  # clamps high
    assert _gradient_at(keys, 0.5) == (128, 128, 128)  # midpoint (rounded)


def test_scene_effects_output_in_range():
    for cls in (SunriseEffect, SunsetEffect, OceanEffect, AmbientEffect):
        eff = cls()
        for _ in range(5):
            r, g, b = eff.update()
            assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255


def test_sunrise_progresses_dark_to_warm():
    s = SunriseEffect(duration=10.0)
    s.start_time = __import__("time").monotonic()        # t≈0 → near night
    r0, g0, b0 = s.update()
    s.start_time -= 100.0                                 # force t>1 → end (warm)
    r1, g1, b1 = s.update()
    assert (r1 + g1 + b1) > (r0 + g0 + b0)               # brighter at the end


def test_audio_mode_degrades_without_backend():
    # Constructing/applying the audio effect must never crash even with no audio
    # backend; update() returns a valid colour and switching modes stops cleanly.
    m = EffectsManager()
    assert m.set_mode("audio", {"r": 0, "g": 120, "b": 255}) is True
    color = m.update()
    assert color is not None and len(color) == 3
    assert all(0 <= c <= 255 for c in color)
    assert m.set_mode("screen_sync") is True             # exercises stop()
    assert m.active_effect is None
