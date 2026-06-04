"""Tests for auto profile switching (FR-PROF-07): matching + switcher + exclusion."""

import sys
import json

from ambilight.auto_profile import match_profile, AutoProfileSwitcher
from ambilight.config import AppConfig, ConfigManager
from ambilight import foreground


def test_match_profile_first_match_substring_and_default():
    rules = [
        {"match": "game.exe", "profile": "gaming"},
        {"match": "vlc", "profile": "movie"},
    ]
    assert match_profile("game.exe", rules, "idle") == "gaming"
    assert match_profile("VLC.EXE", rules, "idle") == "movie"     # case-insensitive substring
    assert match_profile("explorer.exe", rules, "idle") == "idle"  # default fallback
    assert match_profile("explorer.exe", rules, "") is None        # no default → None
    assert match_profile(None, rules, "idle") == "idle"
    assert match_profile("game.exe", [{"match": "game.exe", "profile": ""}], "") is None  # empty profile ignored


def _cfg(enabled=True, default="", rules=None):
    c = AppConfig()
    c.auto_profile.enabled = enabled
    c.auto_profile.default_profile = default
    c.auto_profile.rules = rules or []
    return c


def test_switcher_applies_only_on_change():
    applied = []
    app = ["game.exe"]
    sw = AutoProfileSwitcher(
        _cfg(rules=[{"match": "game.exe", "profile": "gaming"}]),
        get_app=lambda: app[0],
        apply_profile=lambda n: (applied.append(n), True)[1],
    )
    assert sw.tick() == "gaming"
    assert sw.tick() is None          # same foreground → no re-apply
    assert applied == ["gaming"]
    app[0] = "notepad.exe"            # no rule, no default → unchanged
    assert sw.tick() is None
    assert applied == ["gaming"]


def test_switcher_reverts_to_default():
    applied = []
    app = ["game.exe"]
    sw = AutoProfileSwitcher(
        _cfg(default="idle", rules=[{"match": "game.exe", "profile": "gaming"}]),
        get_app=lambda: app[0],
        apply_profile=lambda n: (applied.append(n), True)[1],
    )
    sw.tick()                          # gaming
    app[0] = "chrome.exe"
    assert sw.tick() == "idle"         # falls back to default
    assert applied == ["gaming", "idle"]


def test_switcher_disabled_is_noop():
    applied = []
    sw = AutoProfileSwitcher(
        _cfg(enabled=False, rules=[{"match": "x", "profile": "p"}]),
        get_app=lambda: "x.exe",
        apply_profile=lambda n: applied.append(n),
    )
    assert sw.tick() is None
    assert applied == []


def test_update_config_refreshes_rules():
    sw = AutoProfileSwitcher(_cfg(enabled=False), get_app=lambda: "x", apply_profile=lambda n: True)
    assert sw.enabled is False
    sw.update_config(_cfg(enabled=True, default="d", rules=[{"match": "a", "profile": "b"}]))
    assert sw.enabled is True and sw.default_profile == "d" and len(sw.rules) == 1


def test_foreground_is_none_safe_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert foreground.get_foreground_app() is None      # graceful, no raise


def test_config_default_auto_profile():
    ap = AppConfig().auto_profile
    assert ap.enabled is False and ap.poll_interval == 2.0 and ap.rules == [] and ap.default_profile == ""


def test_profiles_exclude_auto_profile(tmp_path):
    from ambilight.profile_manager import ProfileManager
    cfg = AppConfig()
    cfg.auto_profile.enabled = True
    ConfigManager._instance = cfg
    ConfigManager._loaded_path = str(tmp_path / "cfg.yaml")
    pm = ProfileManager(profiles_dir=tmp_path)

    pm.save_profile("game")
    data = pm.get_profile("game")
    assert "auto_profile" not in data and "color" in data    # save excludes meta-setting

    # A profile file that (wrongly) carries auto_profile must not clobber the rules.
    (tmp_path / "evil.json").write_text(json.dumps({"auto_profile": {"enabled": False}, "color": {"mode": "average"}}))
    pm.apply_profile("evil")
    assert ConfigManager.get().auto_profile.enabled is True   # preserved
    assert ConfigManager.get().color.mode == "average"        # profile still applied
