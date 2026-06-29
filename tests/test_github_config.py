"""Tests for GithubConfig defaults and normalization/validation."""

from ambilight.config import (
    AppConfig,
    GithubConfig,
    ConfigManager,
    DEFAULT_GITHUB_RULES,
    DEFAULT_GITHUB_RULES_VERSION,
)


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


def test_existing_install_tops_up_missing_defaults():
    # Simulate an install seeded under an older defaults version with one custom rule.
    cfg = AppConfig()
    g = cfg.github
    g.rules_seeded = True
    g.rules_version = 0
    g.rules = [{"scope": "workflow", "repo": "me/app", "workflow": "CI",
                "event_type": "workflow_run", "action": "failure", "color": [230, 51, 51]}]
    ConfigManager._normalize_and_validate(cfg)
    # the user's custom rule is preserved untouched
    custom = [r for r in g.rules if r["scope"] == "workflow" and r["repo"] == "me/app"]
    assert custom and custom[0]["color"] == [230, 51, 51]
    # the missing defaults (incl. the global CI-failure rule) were merged in
    assert any(r["scope"] == "global" and r["event_type"] == "workflow_run"
               and r["action"] == "failure" for r in g.rules)
    assert len(g.rules) == len(DEFAULT_GITHUB_RULES) + 1
    assert g.rules_version == DEFAULT_GITHUB_RULES_VERSION


def test_topup_is_idempotent_and_skips_duplicates():
    cfg = AppConfig()
    g = cfg.github
    g.rules_seeded = True
    g.rules_version = 0
    # A custom rule whose signature matches a default (global push) must not be duplicated.
    g.rules = [{"scope": "global", "event_type": "push", "action": "", "color": [1, 2, 3]}]
    ConfigManager._normalize_and_validate(cfg)
    first = len(g.rules)
    push = [r for r in g.rules if r["event_type"] == "push"]
    assert len(push) == 1 and push[0]["color"] == [1, 2, 3]   # default push deduped, custom kept
    ConfigManager._normalize_and_validate(cfg)                 # second load
    assert len(g.rules) == first                              # version now current → no re-append


def test_topup_only_adds_newer_version_defaults(monkeypatch):
    """A version bump tops up only the new version's defaults; a default the user
    deleted under an earlier version is not resurrected."""
    from ambilight import config as cfgmod

    new_rule = {"scope": "global", "event_type": "sponsorship", "action": "", "color": [1, 2, 3]}
    monkeypatch.setattr(
        cfgmod, "DEFAULT_GITHUB_RULES_BY_VERSION",
        {**cfgmod.DEFAULT_GITHUB_RULES_BY_VERSION, 2: [new_rule]},
    )
    monkeypatch.setattr(cfgmod, "DEFAULT_GITHUB_RULES_VERSION", 2)

    cfg = AppConfig()
    g = cfg.github
    g.rules_seeded = True
    g.rules_version = 1          # was current under v1...
    # ...but the user deleted the built-in global "push" default before upgrading.
    g.rules = [{"scope": "global", "event_type": "issue", "action": "opened", "color": [5, 5, 5]}]
    ConfigManager._normalize_and_validate(cfg)

    # the v2 default is merged in
    assert any(r["event_type"] == "sponsorship" for r in g.rules)
    # the deleted v1 default ("push") is NOT resurrected by the v1→v2 top-up
    assert not any(r["event_type"] == "push" for r in g.rules)
    assert g.rules_version == 2


def test_deleted_default_not_resurrected_when_version_current():
    cfg = AppConfig()
    g = cfg.github
    g.rules_seeded = True
    g.rules_version = DEFAULT_GITHUB_RULES_VERSION             # already up to date
    g.rules = [{"scope": "global", "event_type": "issue", "action": "opened", "color": [1, 1, 1]}]
    ConfigManager._normalize_and_validate(cfg)
    assert len(g.rules) == 1                                   # no merge ran


def test_pristine_explicit_rules_are_not_topped_up():
    # rules_seeded False (never seeded) → explicit rules are only cleaned, not merged.
    cfg = AppConfig()
    cfg.github.rules = [{"scope": "global", "event_type": "release", "action": "", "color": [9, 9, 9]}]
    ConfigManager._normalize_and_validate(cfg)
    assert len(cfg.github.rules) == 1


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
