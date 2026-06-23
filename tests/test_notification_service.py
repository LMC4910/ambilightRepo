"""Tests for NotificationFlashService: colour resolution, dedup, throttle, DND."""

import pytest

from ambilight.config import AppConfig
from ambilight.notifications.base import NotificationEvent
from ambilight.notifications.service import NotificationFlashService


class FakeController:
    def __init__(self):
        self.flashes = []

    def flash(self, color, pattern):
        self.flashes.append((tuple(color), pattern))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _event(app_id="discord", app_name="Discord", title="t", body="b", icon=None, source="windows"):
    return NotificationEvent(
        app_id=app_id, app_name=app_name, title=title, body=body,
        icon_bytes=icon, source=source, received_at=0.0,
    )


def _hermetic_cache(monkeypatch):
    """Patch cache I/O on the class *before* instantiation so __init__ never
    reads ~/.ambilight and saves never touch host state (keeps tests
    deterministic regardless of the developer's machine)."""
    monkeypatch.setattr(NotificationFlashService, "_load_cache", lambda self: None)
    monkeypatch.setattr(NotificationFlashService, "_save_cache", lambda self: None)


def _service(monkeypatch, **overrides):
    _hermetic_cache(monkeypatch)
    cfg = AppConfig()
    n = cfg.notifications
    n.enabled = True
    n.min_flash_interval_s = 0.0   # isolate dedup unless a test overrides
    n.dedup_window_s = 5.0
    for k, v in overrides.items():
        setattr(n, k, v)
    ctrl = FakeController()
    clock = Clock()
    svc = NotificationFlashService(
        cfg, ctrl, loop=None,
        listener_factory=lambda on, loop: None, clock=clock,
    )
    return svc, ctrl, clock


def test_per_app_override_wins(monkeypatch):
    svc, ctrl, _ = _service(monkeypatch, app_overrides={"discord": [1, 2, 3]})
    assert svc.resolve_color(_event()) == (1, 2, 3)


def test_override_matches_by_display_name(monkeypatch):
    svc, _, _ = _service(monkeypatch, app_overrides={"Discord": [9, 8, 7]})
    assert svc.resolve_color(_event(app_id="com.discord", app_name="Discord")) == (9, 8, 7)


def test_keyword_rule_for_forwarded_notification(monkeypatch):
    svc, _, _ = _service(monkeypatch, keyword_rules=[{"keyword": "instagram", "color": [255, 0, 255]}])
    ev = _event(app_id="phonelink", app_name="Phone Link", title="Instagram", body="liked your photo")
    assert svc.resolve_color(ev) == (255, 0, 255)


def test_keyword_is_case_insensitive_substring(monkeypatch):
    svc, _, _ = _service(monkeypatch, keyword_rules=[{"keyword": "whatsapp", "color": [1, 1, 1]}])
    ev = _event(app_name="Phone Link", title="WhatsApp Messenger", body="hi")
    assert svc.resolve_color(ev) == (1, 1, 1)


def test_icon_color_cached_and_not_reextracted(monkeypatch):
    svc, _, _ = _service(monkeypatch)
    calls = {"n": 0}

    def fake_extract(icon_bytes, analyzer=None):
        calls["n"] += 1
        return (40, 50, 60)

    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color", fake_extract)
    ev = _event(app_id="slack", icon=b"PNGDATA")
    assert svc.resolve_color(ev) == (40, 50, 60)
    assert svc.resolve_color(ev) == (40, 50, 60)
    assert calls["n"] == 1            # second lookup hits the cache


def test_no_icon_falls_back_to_default(monkeypatch):
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color", lambda *a, **k: None)
    assert svc.resolve_color(_event(app_id="noicon", icon=b"x")) == (7, 7, 7)


def test_missing_icon_bytes_not_cached(monkeypatch):
    # No icon payload at all → fall back, but DON'T persist the no-icon sentinel,
    # so a later notification that carries an icon can still populate the colour.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    assert svc.resolve_color(_event(app_id="later", icon=None)) == (7, 7, 7)
    assert "later" not in svc._color_cache


def test_corrupt_cache_resets_to_empty(monkeypatch, tmp_path):
    # A non-dict cache file must be ignored (not crash _on_notification later).
    cache = tmp_path / "notification_colors.json"
    cache.write_text("[1, 2, 3]")   # a list, not a dict
    monkeypatch.setattr("ambilight.notifications.service._CACHE_PATH", str(cache))
    cfg = AppConfig()
    cfg.notifications.enabled = True
    svc = NotificationFlashService(cfg, FakeController(), loop=None,
                                   listener_factory=lambda on, loop: None, clock=Clock())
    assert svc._color_cache == {}


def test_fixed_mode_always_default(monkeypatch):
    svc, _, _ = _service(monkeypatch, color_mode="fixed", default_color=[5, 6, 7])
    # Even with an icon present, fixed mode ignores it.
    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color",
                        lambda *a, **k: (1, 1, 1))
    assert svc.resolve_color(_event(icon=b"x")) == (5, 6, 7)


def test_disabled_does_not_dispatch(monkeypatch):
    svc, ctrl, _ = _service(monkeypatch)
    svc.enabled = False
    svc._on_notification(_event())
    assert ctrl.flashes == []


def test_dedup_drops_identical_within_window(monkeypatch):
    svc, ctrl, clock = _service(monkeypatch)
    svc._on_notification(_event())
    clock.t = 1.0
    svc._on_notification(_event())          # identical, within 5 s
    assert len(ctrl.flashes) == 1
    clock.t = 7.0
    svc._on_notification(_event())          # window elapsed → fires again
    assert len(ctrl.flashes) == 2


def test_throttle_drops_burst(monkeypatch):
    svc, ctrl, clock = _service(monkeypatch, min_flash_interval_s=2.0, dedup_window_s=0.0)
    svc._on_notification(_event(title="a"))
    svc._on_notification(_event(title="b"))   # different, but within throttle gap
    assert len(ctrl.flashes) == 1
    clock.t = 3.0
    svc._on_notification(_event(title="c"))
    assert len(ctrl.flashes) == 2


def test_suppress_during_dnd(monkeypatch):
    _hermetic_cache(monkeypatch)
    cfg = AppConfig()
    cfg.notifications.enabled = True
    cfg.notifications.suppress_during_dnd = True
    cfg.notifications.min_flash_interval_s = 0.0
    ctrl = FakeController()
    svc = NotificationFlashService(
        cfg, ctrl, loop=None, listener_factory=lambda on, loop: None,
        clock=Clock(), dnd_probe=lambda: True,
    )
    svc._on_notification(_event())
    assert ctrl.flashes == []


def test_dnd_default_does_not_suppress(monkeypatch):
    # Default suppress_during_dnd is False → flashes fire even if a probe says DND.
    svc, ctrl, _ = _service(monkeypatch, default_color=[1, 1, 1])
    svc._dnd_probe = lambda: True
    svc._on_notification(_event())
    assert len(ctrl.flashes) == 1


def test_test_flash_bypasses_gates(monkeypatch):
    svc, ctrl, _ = _service(monkeypatch)
    svc.enabled = False
    svc.test_flash([3, 3, 3])
    assert ctrl.flashes and ctrl.flashes[0][0] == (3, 3, 3)


def test_pattern_carries_config(monkeypatch):
    svc, ctrl, _ = _service(monkeypatch, blink_count=4, on_ms=90, off_ms=40, brightness=0.5,
                            default_color=[10, 10, 10])
    svc._on_notification(_event())
    _, pattern = ctrl.flashes[0]
    assert pattern == {"blink_count": 4, "on_ms": 90, "off_ms": 40, "brightness": 0.5}
