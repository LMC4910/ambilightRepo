"""Tests for the GitHub event → lighting rule mapper (precedence + matching)."""

from ambilight.integrations.github import mapper
from ambilight.integrations.github.models import GithubEvent


DEFAULT_COLOR = (88, 166, 255)
DEFAULT_PATTERN = {"blink_count": 2, "on_ms": 180, "off_ms": 120, "brightness": 1.0}


def _ev(**kw):
    base = dict(
        id="x", event_type="workflow_run", action="failure",
        title="t", repository="acme/api", organization="acme", workflow="Deploy",
    )
    base.update(kw)
    return GithubEvent(**base)


def _resolve(ev, rules):
    return mapper.resolve(ev, rules, DEFAULT_COLOR, DEFAULT_PATTERN)


def test_workflow_rule_beats_repo_org_global():
    rules = [
        {"scope": "global", "event_type": "workflow_run", "action": "failure", "color": [1, 1, 1]},
        {"scope": "org", "org": "acme", "event_type": "workflow_run", "action": "failure", "color": [2, 2, 2]},
        {"scope": "repo", "repo": "acme/api", "event_type": "workflow_run", "action": "failure", "color": [3, 3, 3]},
        {"scope": "workflow", "repo": "acme/api", "workflow": "Deploy",
         "event_type": "workflow_run", "action": "failure", "color": [4, 4, 4]},
    ]
    rgb, _ = _resolve(_ev(), rules)
    assert rgb == (4, 4, 4)  # workflow scope wins


def test_repo_rule_beats_org_and_global():
    rules = [
        {"scope": "global", "action": "failure", "color": [1, 1, 1]},
        {"scope": "org", "org": "acme", "action": "failure", "color": [2, 2, 2]},
        {"scope": "repo", "repo": "acme/api", "action": "failure", "color": [3, 3, 3]},
    ]
    rgb, _ = _resolve(_ev(), rules)
    assert rgb == (3, 3, 3)


def test_repo_rule_does_not_match_other_repo():
    rules = [{"scope": "repo", "repo": "other/repo", "action": "failure", "color": [9, 9, 9]}]
    rgb, _ = _resolve(_ev(), rules)
    assert rgb == DEFAULT_COLOR  # falls back to default


def test_wildcard_event_and_action():
    rules = [{"scope": "global", "event_type": "*", "action": "*", "color": [5, 6, 7]}]
    rgb, _ = _resolve(_ev(event_type="release", action="published"), rules)
    assert rgb == (5, 6, 7)


def test_action_specific_beats_wildcard_same_scope():
    rules = [
        {"scope": "global", "event_type": "workflow_run", "action": "*", "color": [1, 1, 1]},
        {"scope": "global", "event_type": "workflow_run", "action": "failure", "color": [2, 2, 2]},
    ]
    rgb, _ = _resolve(_ev(), rules)
    assert rgb == (2, 2, 2)  # the more specific (non-wildcard action) rule wins


def test_per_rule_pattern_override():
    rules = [{
        "scope": "global", "action": "failure", "color": [200, 0, 0],
        "blink_count": 6, "on_ms": 90,
    }]
    rgb, pattern = _resolve(_ev(), rules)
    assert rgb == (200, 0, 0)
    assert pattern["blink_count"] == 6
    assert pattern["on_ms"] == 90
    assert pattern["off_ms"] == 120  # untouched default retained


def test_no_rules_uses_default():
    rgb, pattern = _resolve(_ev(), [])
    assert rgb == DEFAULT_COLOR
    assert pattern == DEFAULT_PATTERN


def test_no_default_means_ignore():
    # default_color None => unmatched events are skipped entirely.
    assert mapper.resolve(_ev(), [], None, DEFAULT_PATTERN) is None
