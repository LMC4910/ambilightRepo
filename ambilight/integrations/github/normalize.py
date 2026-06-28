"""
GitHub integration — event normalization
========================================
Converts raw GitHub payloads (notification-inbox items, Actions workflow runs,
events-feed objects, and webhook deliveries) into the single :class:`GithubEvent`
model. This is the *only* place that knows GitHub's wire formats — everything
downstream (mapper, store, UI) consumes the normalized model.

Adding a new event type means adding a branch here; unrecognised inputs fall
back to a generic normalized event so the integration still reacts to "anything
GitHub can tell us about" rather than dropping it.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, Optional

from .models import (
    GithubEvent,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
)

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> float:
    """Best-effort ISO-8601 → epoch seconds; falls back to now()."""
    if not value:
        return time.time()
    try:
        from datetime import datetime

        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time()


# --- notifications inbox (GET /notifications) -------------------------------

# GitHub "subject.type" → our event_type taxonomy.
_SUBJECT_TYPE = {
    "Issue": "issue",
    "PullRequest": "pull_request",
    "Release": "release",
    "Discussion": "discussion",
    "Commit": "commit",
    "CheckSuite": "workflow_run",
    "RepositoryVulnerabilityAlert": "security_alert",
    "SecurityAdvisory": "security_alert",
    "RepositoryInvitation": "repository_invitation",
}

# GitHub notification "reason" → our action taxonomy.
_REASON_ACTION = {
    "assign": "assigned",
    "author": "author",
    "comment": "commented",
    "ci_activity": "ci_activity",
    "invitation": "invited",
    "manual": "subscribed",
    "mention": "mentioned",
    "review_requested": "review_requested",
    "security_alert": "security_alert",
    "state_change": "state_change",
    "subscribed": "activity",
    "team_mention": "mentioned",
}

_HIGH_REASONS = {"mention", "team_mention", "review_requested", "assign"}
_CRITICAL_REASONS = {"security_alert"}


def normalize_notification(item: Dict[str, Any], account: str = "") -> GithubEvent:
    subject = item.get("subject") or {}
    repo = item.get("repository") or {}
    full_name = repo.get("full_name", "") or ""
    owner = (repo.get("owner") or {}).get("login", "") or (
        full_name.split("/")[0] if "/" in full_name else ""
    )
    reason = str(item.get("reason", "") or "").strip().lower()
    subj_type = str(subject.get("type", "") or "")
    event_type = _SUBJECT_TYPE.get(subj_type, "notification")
    action = _REASON_ACTION.get(reason, reason or "activity")

    if reason in _CRITICAL_REASONS:
        priority = PRIORITY_CRITICAL
    elif reason in _HIGH_REASONS:
        priority = PRIORITY_HIGH
    else:
        priority = PRIORITY_NORMAL

    title = subject.get("title") or f"{subj_type} in {full_name}".strip()
    # Inbox items don't carry a stable per-update id, so key on the thread id +
    # updated_at to treat each fresh update as a new event but de-dup re-polls.
    nid = str(item.get("id", "")) or full_name
    updated = str(item.get("updated_at", "") or "")
    return GithubEvent(
        id=f"notif-{nid}-{updated}",
        event_type=event_type,
        action=action,
        title=str(title),
        account=account,
        organization=owner,
        repository=full_name,
        actor="",
        priority=priority,
        description=f"{reason} · {subj_type}".strip(" ·"),
        url=str(subject.get("url", "") or ""),
        timestamp=_parse_ts(item.get("updated_at")),
        source="poll",
        payload={"reason": reason, "subject_type": subj_type},
    )


# --- Actions workflow runs (GET /repos/{repo}/actions/runs) ------------------

def normalize_workflow_run(run: Dict[str, Any], account: str = "",
                           repository: str = "") -> GithubEvent:
    repo = run.get("repository") or {}
    full_name = repository or repo.get("full_name", "") or ""
    owner = (repo.get("owner") or {}).get("login", "") or (
        full_name.split("/")[0] if "/" in full_name else ""
    )
    status = str(run.get("status", "") or "").strip().lower()          # queued|in_progress|completed
    conclusion = str(run.get("conclusion", "") or "").strip().lower()  # success|failure|cancelled|...
    # Action is the conclusion when finished, else the live status.
    action = conclusion or status or "unknown"
    name = str(run.get("name", "") or run.get("display_title", "") or "Workflow")
    actor = (run.get("actor") or {}).get("login", "") or ""

    if conclusion == "failure":
        priority = PRIORITY_HIGH
    elif conclusion in ("success", "cancelled", "skipped"):
        priority = PRIORITY_LOW
    else:
        priority = PRIORITY_NORMAL

    run_id = run.get("id", "")
    return GithubEvent(
        id=f"wf-{run_id}-{status}-{conclusion}",
        event_type="workflow_run",
        action=action,
        title=f"{name}: {action}",
        account=account,
        organization=owner,
        repository=full_name,
        workflow=name,
        actor=actor,
        priority=priority,
        description=f"run #{run.get('run_number', '')}".strip(),
        url=str(run.get("html_url", "") or ""),
        timestamp=_parse_ts(run.get("updated_at") or run.get("created_at")),
        source="poll",
        payload={"status": status, "conclusion": conclusion},
    )


# --- events feed (GET /repos/{repo}/events, /orgs/{org}/events) --------------

# GitHub event "type" → (our event_type, default action when payload has none).
_EVENT_TYPE = {
    "PushEvent": ("push", "pushed"),
    "PullRequestEvent": ("pull_request", "opened"),
    "PullRequestReviewEvent": ("pull_request_review", "submitted"),
    "PullRequestReviewCommentEvent": ("review_comment", "created"),
    "IssuesEvent": ("issue", "opened"),
    "IssueCommentEvent": ("issue_comment", "created"),
    "ReleaseEvent": ("release", "published"),
    "CreateEvent": ("branch", "created"),
    "DeleteEvent": ("branch", "deleted"),
    "ForkEvent": ("fork", "forked"),
    "WatchEvent": ("star", "started"),
    "CommitCommentEvent": ("commit_comment", "created"),
    "DeploymentStatusEvent": ("deployment_status", "updated"),
    "WorkflowRunEvent": ("workflow_run", "completed"),
    "DiscussionEvent": ("discussion", "created"),
}


def normalize_event(ev: Dict[str, Any], account: str = "") -> GithubEvent:
    raw_type = str(ev.get("type", "") or "")
    repo = ev.get("repo") or {}
    full_name = str(repo.get("name", "") or "")
    owner = full_name.split("/")[0] if "/" in full_name else ""
    payload = ev.get("payload") or {}

    event_type, default_action = _EVENT_TYPE.get(raw_type, ("activity", "occurred"))
    action = str(payload.get("action", "") or default_action).strip().lower()
    # PRs that merged carry action="closed" + pull_request.merged=True.
    if event_type == "pull_request" and action == "closed":
        if (payload.get("pull_request") or {}).get("merged"):
            action = "merged"
    actor = (ev.get("actor") or {}).get("login", "") or ""

    title = f"{actor} {action} {event_type.replace('_', ' ')} in {full_name}".strip()
    return GithubEvent(
        id=f"ev-{ev.get('id', '')}",
        event_type=event_type,
        action=action,
        title=title,
        account=account,
        organization=owner,
        repository=full_name,
        actor=actor,
        priority=PRIORITY_NORMAL,
        description=raw_type,
        url="",
        timestamp=_parse_ts(ev.get("created_at")),
        source="poll",
        payload={"raw_type": raw_type},
    )


# --- webhook deliveries (X-GitHub-Event header + JSON body) ------------------

# Webhook event name → our event_type. Webhooks carry their own "action" field
# in the body, so we mostly trust it.
_WEBHOOK_TYPE = {
    "push": "push",
    "pull_request": "pull_request",
    "pull_request_review": "pull_request_review",
    "pull_request_review_comment": "review_comment",
    "issues": "issue",
    "issue_comment": "issue_comment",
    "release": "release",
    "create": "branch",
    "delete": "branch",
    "fork": "fork",
    "star": "star",
    "watch": "star",
    "workflow_run": "workflow_run",
    "workflow_job": "workflow_job",
    "check_run": "check_run",
    "check_suite": "workflow_run",
    "deployment": "deployment",
    "deployment_status": "deployment_status",
    "discussion": "discussion",
    "discussion_comment": "discussion_comment",
    "commit_comment": "commit_comment",
    "dependabot_alert": "security_alert",
    "code_scanning_alert": "security_alert",
    "secret_scanning_alert": "security_alert",
    "repository_vulnerability_alert": "security_alert",
}


def normalize_webhook(event_name: str, payload: Dict[str, Any],
                      account: str = "") -> GithubEvent:
    event_name = str(event_name or "").lower()
    repo = payload.get("repository") or {}
    full_name = str(repo.get("full_name", "") or "")
    owner = (repo.get("owner") or {}).get("login", "") or (
        full_name.split("/")[0] if "/" in full_name else ""
    )
    org = (payload.get("organization") or {}).get("login", "") or owner
    sender = (payload.get("sender") or {}).get("login", "") or ""

    event_type = _WEBHOOK_TYPE.get(event_name, event_name or "notification")
    action = str(payload.get("action", "") or "").strip().lower()

    # workflow_run conclusion is the most useful "action" for CI.
    if event_name in ("workflow_run", "check_suite"):
        run = payload.get(event_name) or payload.get("workflow_run") or {}
        conclusion = str(run.get("conclusion", "") or "").strip().lower()
        status = str(run.get("status", "") or "").strip().lower()
        if not isinstance(run, dict) or not run:
            logger.warning("[GitHub] webhook %s missing nested run object; using fallback action path", event_name)
        action = conclusion or status or action or "completed"
    if event_type == "pull_request" and action == "closed":
        if (payload.get("pull_request") or {}).get("merged"):
            action = "merged"
    if not action:
        action = "occurred"

    priority = PRIORITY_NORMAL
    if event_type == "security_alert":
        priority = PRIORITY_CRITICAL
    elif event_type == "workflow_run" and action == "failure":
        priority = PRIORITY_HIGH

    delivery = str(payload.get("_delivery_id") or "").strip()
    if not delivery:
        delivery = f"{event_name}-{uuid.uuid4().hex}"
        logger.warning("[GitHub] webhook missing delivery id; generated %s", delivery)
    workflow = ""
    if event_name in ("workflow_run", "check_suite"):
        run = payload.get(event_name) or payload.get("workflow_run") or {}
        workflow = str(run.get("name", "") or "")
    return GithubEvent(
        id=f"hook-{delivery}",
        event_type=event_type,
        action=action,
        title=f"{event_type.replace('_', ' ')}: {action} in {full_name}".strip(),
        account=account,
        organization=org,
        repository=full_name,
        workflow=workflow,
        actor=sender,
        priority=priority,
        description=f"webhook · {event_name}",
        url=str((repo.get("html_url") or "")),
        timestamp=time.time(),
        source="webhook",
        payload={"event": event_name},
    )
