"""Tests for GithubConfig defaults and normalization/validation."""

from ambilight.config import AppConfig, GithubConfig, ConfigManager


def test_defaults():
    g = AppConfig().github
    assert g.enabled is False
    assert g.default_color == [88, 166, 255]
    assert g.poll_interval_s == 60.0
    assert g.watch_notifications is True
    assert g.scopes == ["notifications", "read:org", "repo"]
    assert g.rules == []


def test_poll_interval_floored():
    cfg = AppConfig()
    cfg.github.poll_interval_s = 1.0          # below the 15s floor
    ConfigManager._normalize_and_validate(cfg)
    assert cfg.github.poll_interval_s == 15.0


def test_color_and_pattern_clamped():
    cfg = AppConfig()
    g = cfg.github
    g.default_color = [300, -5, "20"]
    g.brightness = 9.0
    g.blink_count = 0
    g.on_ms = -10
    ConfigManager._normalize_and_validate(cfg)
    assert g.default_color == [255, 0, 20]
    assert g.brightness == 1.0
    assert g.blink_count == 1
    assert g.on_ms == 20


def test_rules_cleaned_and_scoped():
    cfg = AppConfig()
    cfg.github.rules = [
        {"scope": "WORKFLOW", "repo": "acme/api", "workflow": "Deploy",
         "event_type": "workflow_run", "action": "failure", "color": [255, 0, 0],
         "blink_count": 6},
        {"scope": "bogus", "color": [0, 255, 0]},        # scope coerced to global
        "not-a-dict",                                      # dropped
        {"color": [600, 0, 0]},                            # color clamped, scope->global
    ]
    ConfigManager._normalize_and_validate(cfg)
    rules = cfg.github.rules
    assert len(rules) == 3
    assert rules[0]["scope"] == "workflow"
    assert rules[0]["color"] == [255, 0, 0]
    assert rules[0]["blink_count"] == 6
    assert rules[1]["scope"] == "global"
    assert rules[2]["color"] == [255, 0, 0]


def test_watch_lists_sanitised():
    cfg = AppConfig()
    cfg.github.watched_repos = ["acme/api", "  ", "acme/web "]
    cfg.github.watched_orgs = ["acme", ""]
    ConfigManager._normalize_and_validate(cfg)
    assert cfg.github.watched_repos == ["acme/api", "acme/web"]
    assert cfg.github.watched_orgs == ["acme"]


def test_update_roundtrip_persists(tmp_path):
    path = tmp_path / "configuration.yaml"
    ConfigManager.load(path)
    ConfigManager.update({"github": {"enabled": True, "watched_repos": ["a/b"]}}, path)
    reloaded = ConfigManager.load(path)
    assert reloaded.github.enabled is True
    assert reloaded.github.watched_repos == ["a/b"]
