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


# A made-up app that is NOT in the brand table, so the brand layer falls through
# and the live icon-extraction path is exercised.
_UNKNOWN = dict(app_id="com.acme.internaltool", app_name="Acme Internal Tool")


def test_icon_color_cached_and_not_reextracted(monkeypatch):
    svc, _, _ = _service(monkeypatch)
    calls = {"n": 0}

    def fake_extract(icon_bytes, analyzer=None):
        calls["n"] += 1
        return (40, 50, 60)

    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color", fake_extract)
    ev = _event(icon=b"PNGDATA", **_UNKNOWN)
    assert svc.resolve_color(ev) == (40, 50, 60)
    assert svc.resolve_color(ev) == (40, 50, 60)
    assert calls["n"] == 1            # second lookup hits the cache


def test_no_icon_falls_back_to_default(monkeypatch):
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color", lambda *a, **k: None)
    assert svc.resolve_color(_event(icon=b"x", **_UNKNOWN)) == (7, 7, 7)


def test_missing_icon_bytes_not_cached(monkeypatch):
    # No icon payload at all → fall back, but DON'T persist the no-icon sentinel,
    # so a later notification that carries an icon can still populate the colour.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    assert svc.resolve_color(_event(icon=None, **_UNKNOWN)) == (7, 7, 7)
    assert _UNKNOWN["app_id"] not in svc._color_cache


def test_brand_colour_for_known_app(monkeypatch):
    # Known app, no override / keyword / icon → its official brand colour, not the
    # white default. Discord's brand colour is #5865F2.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    assert svc.resolve_color(_event(app_id="discord", app_name="Discord", icon=None)) == (88, 101, 242)


def test_override_beats_brand(monkeypatch):
    svc, _, _ = _service(monkeypatch, app_overrides={"Discord": [1, 2, 3]})
    assert svc.resolve_color(_event(app_name="Discord")) == (1, 2, 3)


def test_keyword_beats_brand(monkeypatch):
    svc, _, _ = _service(monkeypatch, keyword_rules=[{"keyword": "discord", "color": [9, 9, 9]}])
    assert svc.resolve_color(_event(app_name="Discord")) == (9, 9, 9)


def test_brand_beats_icon_and_skips_extraction(monkeypatch):
    svc, _, _ = _service(monkeypatch)
    called = {"n": 0}

    def fake_extract(icon_bytes, analyzer=None):
        called["n"] += 1
        return (1, 1, 1)

    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color", fake_extract)
    # Known app carrying an icon: brand colour wins and the icon is never extracted.
    assert svc.resolve_color(_event(app_name="Discord", icon=b"PNG")) == (88, 101, 242)
    assert called["n"] == 0


def test_brand_matched_via_app_id(monkeypatch):
    # Display name unknown, but the AUMID carries the brand token.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    ev = _event(app_id="com.squirrel.Discord.Discord", app_name="", icon=None)
    assert svc.resolve_color(ev) == (88, 101, 242)


def test_fixed_mode_skips_brand(monkeypatch):
    # Fixed mode forces the default even for a known brand.
    svc, _, _ = _service(monkeypatch, color_mode="fixed", default_color=[5, 6, 7])
    assert svc.resolve_color(_event(app_name="Discord", icon=None)) == (5, 6, 7)


def test_forwarded_notification_uses_source_brand(monkeypatch):
    # Phone Link mirrors an Instagram DM: the flash uses Instagram's colour
    # (#FF0069), NOT the bridge's. The source app is named in the title.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    ev = _event(app_id="Microsoft.YourPhone_8wekyb3d8bbwe!App", app_name="Phone Link",
                title="Instagram", body="someone liked your photo", icon=None)
    assert svc.resolve_color(ev) == (255, 0, 105)


def test_forwarded_keyword_rule_still_wins(monkeypatch):
    # An explicit keyword rule takes priority over auto source detection.
    svc, _, _ = _service(monkeypatch, keyword_rules=[{"keyword": "instagram", "color": [1, 2, 3]}])
    ev = _event(app_name="Phone Link", app_id="phonelink", title="Instagram", body="hi", icon=None)
    assert svc.resolve_color(ev) == (1, 2, 3)


def test_forwarded_without_known_source_falls_through(monkeypatch):
    # A forwarder whose text names no known app → no false colour; falls back to
    # the default (the bridge id here carries no brand token).
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    ev = _event(app_name="Phone Link", app_id="phonelink", title="Mom", body="call me", icon=None)
    assert svc.resolve_color(ev) == (7, 7, 7)


def test_non_forwarder_does_not_text_scan(monkeypatch):
    # A normal app whose message mentions another brand must NOT borrow its colour:
    # a Discord message referencing Spotify still flashes Discord's brand colour.
    svc, _, _ = _service(monkeypatch)
    ev = _event(app_id="discord", app_name="Discord", title="friend", body="listen on Spotify", icon=None)
    assert svc.resolve_color(ev) == (88, 101, 242)


def test_forwarded_uses_source_icon_when_text_unknown(monkeypatch):
    # A Discord alert forwarded by Phone Link with no "discord" in the text: the
    # toast carries Discord's icon, so the icon colour is used — NOT the bridge's
    # Microsoft-blue (which the old code produced via the AUMID "Microsoft" token).
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color",
                        lambda *a, **k: (10, 20, 30))
    ev = _event(app_id="Microsoft.YourPhone_8wekyb3d8bbwe!App", app_name="Phone Link",
                title="A friend", body="sent a message", icon=b"PNG")
    assert svc.resolve_color(ev) == (10, 20, 30)


def test_forwarded_icon_not_shared_across_sources(monkeypatch):
    # The bridge app_id is identical for every forwarded app, so forwarded icons
    # must be extracted fresh — never cached under the bridge id, or the 2nd app
    # would reuse the 1st app's colour.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    colours = iter([(10, 10, 10), (20, 20, 20)])
    monkeypatch.setattr("ambilight.notifications.service.icon_dominant_color",
                        lambda *a, **k: next(colours))
    bridge = "Microsoft.YourPhone_8wekyb3d8bbwe!App"
    a = svc.resolve_color(_event(app_id=bridge, app_name="Phone Link", title="x", body="y", icon=b"A"))
    b = svc.resolve_color(_event(app_id=bridge, app_name="Phone Link", title="x", body="y", icon=b"B"))
    assert a == (10, 10, 10) and b == (20, 20, 20)
    assert bridge not in svc._color_cache


def test_forwarded_never_flashes_bridge_brand(monkeypatch):
    # No source text and no icon → default, never the bridge publisher's colour.
    svc, _, _ = _service(monkeypatch, default_color=[7, 7, 7])
    ev = _event(app_id="Microsoft.YourPhone_8wekyb3d8bbwe!App", app_name="Phone Link",
                title="Mom", body="call me", icon=None)
    assert svc.resolve_color(ev) == (7, 7, 7)


def test_override_is_case_insensitive(monkeypatch):
    # "compare app names in small case": an override keyed "DISCORD" matches "Discord".
    svc, _, _ = _service(monkeypatch, app_overrides={"DISCORD": [5, 5, 5]})
    assert svc.resolve_color(_event(app_id="discord", app_name="Discord")) == (5, 5, 5)


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
