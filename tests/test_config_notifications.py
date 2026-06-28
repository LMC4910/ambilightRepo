"""Tests for NotificationConfig defaults, normalization, and round-trip."""

import dataclasses

from ambilight.config import AppConfig, NotificationConfig, ConfigManager


def test_defaults():
    n = AppConfig().notifications
    assert n.enabled is False
    assert n.default_color == [255, 255, 255]
    assert n.color_mode == "icon"
    assert n.suppress_during_dnd is False     # flashes during DND by default
    assert n.flash_when_locked is True        # flashes while locked by default
    assert n.blink_count == 2
    assert n.inter_flash_gap_ms == 120        # dark gap between queued flashes
    assert n.flash_max_retries == 3           # retry a failed flash 3x before moving on


def test_flash_queue_fields_clamped():
    cfg = AppConfig()
    n = cfg.notifications
    n.inter_flash_gap_ms = -50                 # below floor
    n.flash_max_retries = 0                    # below floor (need at least 1 attempt)
    ConfigManager._normalize_and_validate(cfg)
    assert n.inter_flash_gap_ms == 0           # clamped to 0 (no negative gap)
    assert n.flash_max_retries == 1            # clamped to a minimum of 1


def test_normalization_clamps_and_coerces():
    cfg = AppConfig()
    n = cfg.notifications
    n.brightness = 5.0
    n.blink_count = 0
    n.on_ms = -10
    n.color_mode = "bogus"
    n.default_color = [300, -5, "20"]
    n.keyword_rules = [
        {"keyword": "  insta  ", "color": [10, 20, 30]},
        {"keyword": "", "color": [0, 0, 0]},     # dropped (no keyword)
        "not a dict",                             # dropped
    ]
    n.app_overrides = {"Discord": [400, 10, 10]}
    ConfigManager._normalize_and_validate(cfg)

    assert n.brightness == 1.0
    assert n.blink_count == 1
    assert n.on_ms == 20                          # min floor
    assert n.color_mode == "icon"                 # unknown → default
    assert n.default_color == [255, 0, 20]        # clamped + coerced
    assert n.keyword_rules == [{"keyword": "insta", "color": [10, 20, 30]}]
    assert n.app_overrides == {"Discord": [255, 10, 10]}


def test_dict_round_trip_preserves_section():
    from ambilight.config import _dict_to_dataclass
    raw = {
        "notifications": {
            "enabled": True,
            "default_color": [1, 2, 3],
            "keyword_rules": [{"keyword": "x", "color": [4, 5, 6]}],
        }
    }
    cfg = _dict_to_dataclass(AppConfig, raw)
    assert cfg.notifications.enabled is True
    assert cfg.notifications.default_color == [1, 2, 3]
    # asdict survives serialization (used by ConfigManager.save)
    d = dataclasses.asdict(cfg)
    assert d["notifications"]["keyword_rules"] == [{"keyword": "x", "color": [4, 5, 6]}]


def test_is_dataclass():
    assert dataclasses.is_dataclass(NotificationConfig)
