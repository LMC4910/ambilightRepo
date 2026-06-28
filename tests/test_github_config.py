"""Tests for GithubConfig defaults and normalization/validation."""

from ambilight.config import AppConfig, GithubConfig, ConfigManager


def test_defaults():
    g = AppConfig().github
    assert g.enabled is False
    assert g.default_color == [88, 166, 255]
    assert g.poll_interval_s == 60.0
    assert g.watch_notifications is True
    assert g.scopes == ["notifications", "read:org", "repo"]
    assert g.rules == []            # raw dataclass default (seeded at normalize time)
    assert g.rules_seeded is False


def test_default_rules_seeded_on_first_normalize():
    cfg = AppConfig()
    assert cfg.github.rules == []
    ConfigManager._normalize_and_validate(cfg)
    assert cfg.github.rules_seeded is True
    assert len(cfg.github.rules) > 20
    # the headline CI-failure rule is present and red
    fail = [r for r in cfg.github.rules
            if r["event_type"] == "workflow_run" and r["action"] == "failure"]
    assert fail and fail[0]["color"] == [220, 38, 38]
    # non-core event types are also seeded
    invitation = [r for r in cfg.github.rules if r["event_type"] == "repository_invitation"]
    assert invitation


def test_cleared_rules_are_reseeded():
    cfg = AppConfig()
    ConfigManager._normalize_and_validate(cfg)        # seeds + marks seeded
    cfg.github.rules = []                              # user clears all rules
    ConfigManager._normalize_and_validate(cfg)        # auto re-seeds
    assert cfg.github.rules
    assert cfg.github.rules_seeded is True


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
