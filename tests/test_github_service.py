"""End-to-end (in-process, no network) tests for GithubIntegration:
event → rule → flash, webhook ingest + dedup, and a full poll cycle.
"""

import asyncio

from ambilight.config import AppConfig, ConfigManager, DEFAULT_GITHUB_RULES_VERSION
from ambilight.integrations.github import api as api_mod
from ambilight.integrations.github.models import GithubEvent
from ambilight.integrations.github.service import GithubIntegration
from ambilight.integrations.github.store import GithubStore


class FakeController:
    def __init__(self):
        self.flashes = []

    def flash(self, color, pattern, label=None):
        self.flashes.append((tuple(color), pattern, label))


def _cfg(**gh):
    cfg = AppConfig()
    cfg.github.enabled = True
    # Tests control rules explicitly: mark as already seeded at the current
    # defaults version so neither first-run seeding nor the version top-up runs.
    cfg.github.rules_seeded = True
    cfg.github.rules_version = DEFAULT_GITHUB_RULES_VERSION
    for k, v in gh.items():
        setattr(cfg.github, k, v)
    ConfigManager._normalize_and_validate(cfg)
    return cfg


def _integration(cfg, store_path):
    gi = GithubIntegration(cfg, FakeController(), loop=None)
    gi._store = GithubStore(path=store_path)   # hermetic DB
    return gi


def test_dispatch_maps_event_to_flash(tmp_path):
    cfg = _cfg(rules=[{"scope": "repo", "repo": "acme/api",
                       "event_type": "workflow_run", "action": "failure",
                       "color": [220, 40, 40]}])
    gi = _integration(cfg, tmp_path / "g.db")
    ev = GithubEvent(id="1", event_type="workflow_run", action="failure",
                     title="CI failed", repository="acme/api", organization="acme")
    asyncio.run(gi._dispatch(ev))
    assert gi._controller.flashes
    rgb, pattern, label = gi._controller.flashes[0]
    assert rgb == (220, 40, 40)
    assert "GitHub" in label


def test_dispatch_uses_default_when_no_rule(tmp_path):
    cfg = _cfg(default_color=[10, 20, 30])
    gi = _integration(cfg, tmp_path / "g.db")
    ev = GithubEvent(id="1", event_type="custom_event", action="published", title="v1")
    asyncio.run(gi._dispatch(ev))
    assert gi._controller.flashes[0][0] == (10, 20, 30)


def test_ingest_webhook_flashes_and_dedups(tmp_path):
    cfg = _cfg(rules=[{"scope": "global", "event_type": "workflow_run",
                       "action": "failure", "color": [255, 0, 0]}])
    gi = _integration(cfg, tmp_path / "g.db")
    payload = {
        "repository": {"full_name": "acme/api", "owner": {"login": "acme"}},
        "workflow_run": {"name": "CI", "status": "completed", "conclusion": "failure"},
    }
    asyncio.run(gi.ingest_webhook("workflow_run", payload, delivery_id="d1"))
    asyncio.run(gi.ingest_webhook("workflow_run", payload, delivery_id="d1"))  # duplicate
    assert len(gi._controller.flashes) == 1          # deduped on delivery id
    assert gi._controller.flashes[0][0] == (255, 0, 0)


# --- full poll cycle with a fake API (no httpx/network) ---------------------

def _resp(data, headers=None):
    return api_mod.Response(200, data, headers or {})


class FakeApi:
    def __init__(self, runs):
        self._runs = runs
        self.calls = 0

    async def get_notifications(self, etag=None, last_modified=None, all_=False):
        return _resp([])

    async def get_workflow_runs(self, repo, etag=None, per_page=20):
        self.calls += 1
        return _resp({"workflow_runs": self._runs})

    async def get_repo_events(self, repo, etag=None):
        return _resp([])

    async def get_org_events(self, org, etag=None):
        return _resp([])


def test_poller_full_cycle_dedups_across_polls(tmp_path):
    from ambilight.integrations.github.poller import GithubPoller
    from ambilight.integrations.github.health import GithubHealth

    cfg = _cfg(watched_repos=["acme/api"], watch_notifications=True,
               rules=[{"scope": "global", "event_type": "workflow_run",
                       "action": "failure", "color": [200, 0, 0]}])
    gi = _integration(cfg, tmp_path / "g.db")

    runs = [{"id": 7, "name": "Deploy", "status": "completed", "conclusion": "failure",
             "updated_at": "2026-06-01T00:00:00Z", "repository": {"full_name": "acme/api"}}]
    poller = GithubPoller(FakeApi(runs), gi._store, GithubHealth(), gi._dispatch, account="me")
    poller.configure(base_interval=60, watch_notifications=True,
                     watched_repos=["acme/api"], watched_orgs=[])

    async def run_two_cycles():
        await poller._poll_once(suppress=False)   # first real pass: flashes once
        await poller._poll_once(suppress=False)   # same run id: deduped, no new flash

    asyncio.run(run_two_cycles())
    assert len(gi._controller.flashes) == 1
    assert gi._controller.flashes[0][0] == (200, 0, 0)


def test_ci_activity_notification_suppressed_only_for_watched_repos(tmp_path):
    from ambilight.integrations.github.poller import GithubPoller
    from ambilight.integrations.github.health import GithubHealth

    cfg = _cfg(watched_repos=["acme/api"], watch_notifications=True)
    gi = _integration(cfg, tmp_path / "g.db")

    notifs = [
        {"id": "n1", "reason": "ci_activity", "updated_at": "2026-06-01T00:00:00Z",
         "subject": {"type": "CheckSuite", "title": "CI"},
         "repository": {"full_name": "acme/api", "owner": {"login": "acme"}}},   # watched → skipped
        {"id": "n2", "reason": "ci_activity", "updated_at": "2026-06-01T00:00:00Z",
         "subject": {"type": "CheckSuite", "title": "CI"},
         "repository": {"full_name": "other/repo", "owner": {"login": "other"}}},  # unwatched → kept
    ]

    class NotifApi(FakeApi):
        def __init__(self, notifs):
            super().__init__(runs=[])
            self._notifs = notifs

        async def get_notifications(self, etag=None, last_modified=None, all_=False):
            return _resp(self._notifs)

    seen = []

    async def capture(ev):
        seen.append(ev)

    poller = GithubPoller(NotifApi(notifs), gi._store, GithubHealth(), capture, account="me")
    poller.configure(base_interval=60, watch_notifications=True,
                     watched_repos=["acme/api"], watched_orgs=[])
    asyncio.run(poller._poll_once(suppress=False))

    assert sorted(ev.repository for ev in seen) == ["other/repo"]


def test_list_workflows_slims_and_falls_back_to_cache(tmp_path):
    cfg = _cfg()
    gi = _integration(cfg, tmp_path / "g.db")

    class WfApi:
        async def get_repo_workflows(self, repo, per_page=100):
            return [
                {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
                {"id": 2, "name": "", "path": "skip", "state": "active"},   # blank name dropped
            ]

    gi._api = WfApi()
    out = asyncio.run(gi.list_workflows("acme/api"))
    assert out == [{"name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}]

    class BoomApi:
        async def get_repo_workflows(self, repo, per_page=100):
            raise RuntimeError("boom")

    gi._api = BoomApi()
    assert asyncio.run(gi.list_workflows("acme/api")) == out   # served from cache
