"""Tests for effects, scheduler window parsing, and the registry (FR-EFF-03..08)."""

import datetime

from ambilight.effects_engine import (
    EffectsManager, EffectScheduler, CandleEffect, _parse_window, _in_window,
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
