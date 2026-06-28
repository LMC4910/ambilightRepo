"""
GitHub integration — event → lighting mapper
============================================
Resolves a normalized :class:`GithubEvent` to a concrete ``(rgb, pattern)`` the
pipeline can flash, using only the user's configured rules. **There is no brand
/ logo colour lookup** — every colour comes from the Integrations → GitHub tab.

Rule precedence (most specific wins):

    Workflow  →  Repository  →  Organization  →  Global default

A rule is a plain dict (mirrors the notifications ``keyword_rules`` style) with
optional scoping/match fields::

    {
      "scope":      "workflow" | "repo" | "org" | "global",
      "repo":       "owner/name",     # for repo / workflow scope
      "org":        "orgname",        # for org scope
      "workflow":   "Deploy",         # for workflow scope (matches GithubEvent.workflow)
      "event_type": "workflow_run",   # "" or "*" = any
      "action":     "failure",        # "" or "*" = any
      "color":      [r, g, b],
      # optional per-rule pattern overrides:
      "blink_count": 4, "on_ms": 120, "off_ms": 80, "brightness": 1.0
    }
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import GithubEvent

RGB = Tuple[int, int, int]

logger = logging.getLogger(__name__)

# Higher scope score = more specific = wins.
_SCOPE_SCORE = {"global": 0, "org": 1, "repo": 2, "workflow": 3}

_ANY = ("", "*", "any")


def _as_rgb(value: Any, default: RGB) -> RGB:
    try:
        rgb = [max(0, min(255, int(c))) for c in value][:3]
        if len(rgb) == 3:
            return (rgb[0], rgb[1], rgb[2])
    except (TypeError, ValueError):
        pass
    return default


def _matches(rule: Dict[str, Any], ev: GithubEvent) -> Optional[int]:
    """Return a specificity score if *rule* applies to *ev*, else ``None``.

    The score orders matching rules so the most specific one wins: scope weight
    dominates, with non-wildcard event_type/action as tie-breakers.
    """
    scope = str(rule.get("scope", "global") or "global").lower()
    if scope not in _SCOPE_SCORE:
        scope = "global"

    # Scope target must match the event.
    if scope in ("repo", "workflow"):
        want = str(rule.get("repo", "") or "").lower()
        if want and want != ev.repository.lower():
            return None
    if scope == "workflow":
        wf = str(rule.get("workflow", "") or "").lower()
        if wf and wf != ev.workflow.lower():
            return None
    if scope == "org":
        org = str(rule.get("org", "") or "").lower()
        if org and org != ev.organization.lower():
            return None

    # event_type / action filters ("" / "*" = wildcard).
    et = str(rule.get("event_type", "") or "").lower()
    if et not in _ANY and et != ev.event_type.lower():
        return None
    ac = str(rule.get("action", "") or "").lower()
    if ac not in _ANY and ac != ev.action.lower():
        return None

    score = _SCOPE_SCORE[scope] * 10
    if et not in _ANY:
        score += 2
    if ac not in _ANY:
        score += 1
    return score


def resolve(ev: GithubEvent, rules: List[Dict[str, Any]],
            default_color: RGB, default_pattern: Dict[str, Any]
            ) -> Optional[Tuple[RGB, Dict[str, Any]]]:
    """Resolve *ev* to ``(rgb, pattern)``.

    Returns ``None`` when no rule matches *and* there is no usable default — the
    caller treats that as "ignore this event" (so the user can opt to only light
    up on events they've explicitly configured by clearing the global default).
    """
    best: Optional[Tuple[int, int, Dict[str, Any]]] = None  # (score, order, rule)
    for order, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            continue
        score = _matches(rule, ev)
        if score is None:
            continue
        # Higher score wins; for equal scores the earlier rule wins.
        if best is None or score > best[0]:
            best = (score, order, rule)

    if best is not None:
        rule = best[2]
        rgb = _as_rgb(rule.get("color"), default_color)
        pattern = dict(default_pattern)
        for k in ("blink_count", "on_ms", "off_ms", "brightness"):
            if rule.get(k) is not None:
                pattern[k] = rule[k]
        logger.debug(
            "[GitHub] matched rule scope=%s event=%s action=%s repo=%s org=%s workflow=%s for %s/%s",
            rule.get("scope", "global"),
            rule.get("event_type", "*"),
            rule.get("action", "*"),
            rule.get("repo", ""),
            rule.get("org", ""),
            rule.get("workflow", ""),
            ev.event_type,
            ev.action,
        )
        return rgb, pattern

    # No rule matched — fall back to the global default colour if the user kept
    # one. An explicitly-empty default means "don't flash for unmatched events".
    if default_color is None:
        logger.debug("[GitHub] no rule matched %s/%s and default color disabled", ev.event_type, ev.action)
        return None
    logger.debug("[GitHub] no rule matched %s/%s; using default color", ev.event_type, ev.action)
    return _as_rgb(default_color, (88, 166, 255)), dict(default_pattern)
