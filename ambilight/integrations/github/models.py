"""
GitHub integration — data models
================================
The single normalized event shape every GitHub source (notifications inbox,
workflow runs, the events feed, or a webhook) is converted into before it ever
touches the lighting layer. Keeping one model here means the mapper, store, UI
and tests all speak the same language and adding a new GitHub event type is a
change to :mod:`normalize` alone.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# Coarse priority buckets — used as a final tie-breaker and to let the user paint
# "anything important" one colour without enumerating every event type.
PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"


@dataclass
class GithubEvent:
    """A single GitHub activity, normalised across every source.

    ``event_type`` / ``action`` use the integration's own small taxonomy (see
    :mod:`normalize`) rather than raw GitHub strings, so lighting rules are
    written once and match regardless of whether the event arrived via the
    inbox, the events feed, the Actions API, or a webhook.
    """

    id: str                                  # stable de-dup key (source-prefixed)
    event_type: str                          # e.g. "workflow_run", "pull_request", "issue"
    action: str                              # e.g. "success", "failure", "opened", "merged"
    title: str                               # human one-liner for the UI
    plugin: str = "github"
    account: str = ""                        # the connected login that saw this
    organization: str = ""                   # owner / org login ("" for user repos)
    repository: str = ""                     # "owner/name" ("" when not repo-scoped)
    workflow: str = ""                       # workflow name (workflow_run events only)
    actor: str = ""                          # who triggered it
    priority: str = PRIORITY_NORMAL
    description: str = ""
    url: str = ""                            # html link for the UI
    timestamp: float = field(default_factory=time.time)
    source: str = "poll"                     # "poll" | "webhook"
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubEvent":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def event_key(event_type: str, action: str) -> str:
    """Canonical "type/action" key used by the UI and rule matching."""
    return f"{event_type}/{action}" if action else event_type
