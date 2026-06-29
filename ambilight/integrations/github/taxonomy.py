"""
GitHub integration — rule taxonomy (event types + actions per event)
====================================================================
The single source of truth for the *fixed* parts of a colour rule: the event
types we recognise and the action values each one can carry. GitHub has no API
that enumerates these, so they're derived from the webhook docs and our own
normalizers (:mod:`.normalize`). Serving them from here (via ``/api/github/meta``)
lets the UI render every rule field as a dropdown — no free-text typing — and
guarantees the picker never drifts from what the matcher actually sees.

``action`` values blend two sources: what the pollers emit today
(notifications + ``/actions/runs`` + events feed) and the webhook ``action``
field (for the optional webhook receiver). The empty action ``""`` is the
"any action" wildcard and is offered by the UI separately, so it is not listed
here.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Event type → human label. Mirrors the normalizer's taxonomy; "" = any event.
EVENT_TYPES: List[tuple] = [
    ("", "Any event"),
    ("workflow_run", "Workflow run (CI)"),
    ("pull_request", "Pull request"),
    ("pull_request_review", "Pull request review"),
    ("review_comment", "Review comment"),
    ("issue", "Issue"),
    ("issue_comment", "Issue comment"),
    ("release", "Release"),
    ("push", "Push"),
    ("branch", "Branch create/delete"),
    ("fork", "Fork"),
    ("star", "Star"),
    ("discussion", "Discussion"),
    ("discussion_comment", "Discussion comment"),
    ("commit_comment", "Commit comment"),
    ("deployment", "Deployment"),
    ("deployment_status", "Deployment status"),
    ("workflow_job", "Workflow job"),
    ("check_run", "Check run"),
    ("repository_invitation", "Repository invitation"),
    ("security_alert", "Security alert"),
]

# Event type → ordered list of concrete action values (most common first). "" is
# the cross-cutting notification reasons that can ride on any event type.
EVENT_ACTIONS: Dict[str, List[str]] = {
    "": ["mentioned", "review_requested", "assigned", "subscribed", "activity", "state_change"],
    "workflow_run": [
        "failure", "success", "cancelled", "skipped", "timed_out", "action_required",
        "neutral", "stale", "startup_failure", "in_progress", "queued", "requested",
        "completed", "ci_activity",
    ],
    "workflow_job": ["queued", "in_progress", "completed", "waiting"],
    "check_run": ["created", "completed", "rerequested", "requested_action"],
    "pull_request": [
        "opened", "merged", "closed", "reopened", "ready_for_review", "review_requested",
        "review_request_removed", "assigned", "unassigned", "labeled", "unlabeled",
        "synchronize", "edited", "converted_to_draft", "locked", "unlocked",
        "enqueued", "dequeued",
    ],
    "pull_request_review": ["submitted", "edited", "dismissed"],
    "review_comment": ["created", "deleted", "edited"],
    "issue": [
        "opened", "closed", "reopened", "assigned", "unassigned", "labeled", "unlabeled",
        "edited", "pinned", "unpinned", "locked", "unlocked", "transferred", "deleted",
        "milestoned", "demilestoned",
    ],
    "issue_comment": ["created", "deleted", "edited"],
    "release": ["published", "released", "created", "edited", "prereleased", "deleted", "unpublished"],
    "push": ["pushed"],
    "branch": ["created", "deleted"],
    "fork": ["forked"],
    "star": ["created", "started", "deleted"],
    "discussion": [
        "created", "edited", "deleted", "answered", "unanswered", "labeled", "unlabeled",
        "locked", "unlocked", "pinned", "unpinned", "transferred", "category_changed",
        "closed", "reopened",
    ],
    "discussion_comment": ["created", "deleted", "edited"],
    "commit_comment": ["created"],
    "deployment": ["created"],
    "deployment_status": ["updated", "created"],
    "repository_invitation": ["invited"],
    "security_alert": [
        "created", "dismissed", "fixed", "reopened", "reintroduced", "auto_dismissed",
        "auto_reopened", "resolved", "publicly_leaked", "validated", "security_alert",
    ],
}


def meta() -> Dict[str, Any]:
    """JSON-ready taxonomy for the UI: event types (with labels) + actions per event."""
    return {
        "event_types": [{"value": v, "label": label} for v, label in EVENT_TYPES],
        "actions_by_event": {k: list(v) for k, v in EVENT_ACTIONS.items()},
    }
