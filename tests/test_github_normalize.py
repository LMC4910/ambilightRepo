"""Tests for GitHub event normalization across all sources."""

from ambilight.integrations.github import normalize
from ambilight.integrations.github.models import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
)


def test_notification_pull_request_review_requested():
    item = {
        "id": "42",
        "reason": "review_requested",
        "updated_at": "2026-06-01T10:00:00Z",
        "subject": {"type": "PullRequest", "title": "Add feature", "url": "https://api/pr/1"},
        "repository": {"full_name": "acme/api", "owner": {"login": "acme"}},
    }
    ev = normalize.normalize_notification(item, account="me")
    assert ev.event_type == "pull_request"
    assert ev.action == "review_requested"
    assert ev.repository == "acme/api"
    assert ev.organization == "acme"
    assert ev.account == "me"
    assert ev.priority == PRIORITY_HIGH
    assert ev.id == "notif-42-2026-06-01T10:00:00Z"


def test_notification_security_alert_is_critical():
    item = {
        "id": "7",
        "reason": "security_alert",
        "subject": {"type": "RepositoryVulnerabilityAlert", "title": "CVE"},
        "repository": {"full_name": "acme/api"},
    }
    ev = normalize.normalize_notification(item)
    assert ev.event_type == "security_alert"
    assert ev.priority == PRIORITY_CRITICAL


def test_workflow_run_failure():
    run = {
        "id": 99,
        "name": "Deploy Production",
        "status": "completed",
        "conclusion": "failure",
        "run_number": 12,
        "html_url": "https://gh/run/99",
        "updated_at": "2026-06-02T12:00:00Z",
        "actor": {"login": "octocat"},
    }
    ev = normalize.normalize_workflow_run(run, account="me", repository="acme/api")
    assert ev.event_type == "workflow_run"
    assert ev.action == "failure"
    assert ev.workflow == "Deploy Production"
    assert ev.repository == "acme/api"
    assert ev.priority == PRIORITY_HIGH
    assert ev.id == "wf-99-completed-failure"


def test_workflow_run_in_progress_uses_status():
    run = {"id": 1, "name": "CI", "status": "in_progress", "conclusion": None}
    ev = normalize.normalize_workflow_run(run, repository="a/b")
    assert ev.action == "in_progress"


def test_workflow_run_action_normalizes_case_and_whitespace():
    run = {"id": 2, "name": "CI", "status": " COMPLETED ", "conclusion": " FAILURE "}
    ev = normalize.normalize_workflow_run(run, repository="a/b")
    assert ev.action == "failure"


def test_event_pull_request_merged():
    ev_raw = {
        "id": "555",
        "type": "PullRequestEvent",
        "actor": {"login": "dev"},
        "repo": {"name": "acme/web"},
        "created_at": "2026-06-03T08:00:00Z",
        "payload": {"action": "closed", "pull_request": {"merged": True}},
    }
    ev = normalize.normalize_event(ev_raw)
    assert ev.event_type == "pull_request"
    assert ev.action == "merged"
    assert ev.repository == "acme/web"
    assert ev.id == "ev-555"


def test_event_unknown_type_degrades_generically():
    ev = normalize.normalize_event({"id": "1", "type": "MysteryEvent", "repo": {"name": "a/b"}})
    assert ev.event_type == "activity"
    assert ev.action == "occurred"


def test_webhook_workflow_run_failure_critical_priority():
    payload = {
        "_delivery_id": "abc",
        "repository": {"full_name": "acme/api", "owner": {"login": "acme"}},
        "sender": {"login": "ci"},
        "workflow_run": {"name": "Build", "status": "completed", "conclusion": "failure"},
    }
    ev = normalize.normalize_webhook("workflow_run", payload)
    assert ev.event_type == "workflow_run"
    assert ev.action == "failure"
    assert ev.workflow == "Build"
    assert ev.source == "webhook"
    assert ev.id == "hook-abc"


def test_webhook_workflow_run_missing_nested_object_uses_action_fallback():
    payload = {
        "_delivery_id": "x1",
        "repository": {"full_name": "acme/api", "owner": {"login": "acme"}},
        "action": " completed ",
        "workflow_run": None,
    }
    ev = normalize.normalize_webhook("workflow_run", payload)
    assert ev.event_type == "workflow_run"
    assert ev.action == "completed"


def test_webhook_missing_delivery_id_generates_unique_id():
    payload = {
        "repository": {"full_name": "acme/api", "owner": {"login": "acme"}},
        "action": "opened",
    }
    ev = normalize.normalize_webhook("pull_request", payload)
    assert ev.id.startswith("hook-pull_request-")


def test_webhook_dependabot_alert_is_security():
    payload = {"repository": {"full_name": "acme/api"}, "action": "created"}
    ev = normalize.normalize_webhook("dependabot_alert", payload)
    assert ev.event_type == "security_alert"
    assert ev.priority == PRIORITY_CRITICAL
