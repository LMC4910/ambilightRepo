"""The poller must skip repos/orgs a live webhook already covers, while always
polling the notifications inbox (which has no webhook equivalent)."""

import asyncio

from ambilight.integrations.github import api as api_mod
from ambilight.integrations.github.health import GithubHealth
from ambilight.integrations.github.poller import GithubPoller
from ambilight.integrations.github.store import GithubStore


def _resp(data, headers=None):
    return api_mod.Response(200, data, headers or {})


class CountingApi:
    def __init__(self):
        self.notif_calls = 0
        self.runs_calls = []
        self.repo_events_calls = []
        self.org_events_calls = []

    async def get_notifications(self, etag=None, last_modified=None, all_=False):
        self.notif_calls += 1
        return _resp([])

    async def get_workflow_runs(self, repo, etag=None, per_page=20):
        self.runs_calls.append(repo)
        return _resp({"workflow_runs": []})

    async def get_repo_events(self, repo, etag=None):
        self.repo_events_calls.append(repo)
        return _resp([])

    async def get_org_events(self, org, etag=None):
        self.org_events_calls.append(org)
        return _resp([])


def _poller(api, tmp_path, **configure):
    async def _noop(ev):
        pass
    store = GithubStore(path=tmp_path / "g.db")
    p = GithubPoller(api, store, GithubHealth(), _noop, account="me")
    p.configure(**configure)
    return p


def test_covered_repo_is_not_polled(tmp_path):
    api = CountingApi()
    p = _poller(api, tmp_path, base_interval=60, watch_notifications=True,
                watched_repos=["acme/api", "ext/lib"], watched_orgs=[],
                covered_repos={"acme/api"})
    asyncio.run(p._poll_once(suppress=True))
    # acme/api is covered by a webhook → skipped; ext/lib still polled.
    assert api.runs_calls == ["ext/lib"]
    assert api.repo_events_calls == ["ext/lib"]
    # Notifications inbox always polls.
    assert api.notif_calls == 1


def test_covered_org_is_not_polled(tmp_path):
    api = CountingApi()
    p = _poller(api, tmp_path, base_interval=60, watch_notifications=True,
                watched_repos=[], watched_orgs=["acme", "other"],
                covered_orgs={"acme"})
    asyncio.run(p._poll_once(suppress=True))
    assert api.org_events_calls == ["other"]


def test_coverage_matching_is_case_insensitive(tmp_path):
    api = CountingApi()
    p = _poller(api, tmp_path, base_interval=60, watch_notifications=False,
                watched_repos=["Acme/API"], watched_orgs=[],
                covered_repos={"acme/api"})
    asyncio.run(p._poll_once(suppress=True))
    assert api.runs_calls == []           # matched despite case difference
    assert api.notif_calls == 0           # notifications disabled here


def test_no_coverage_polls_everything(tmp_path):
    api = CountingApi()
    p = _poller(api, tmp_path, base_interval=60, watch_notifications=True,
                watched_repos=["acme/api"], watched_orgs=["acme"])
    asyncio.run(p._poll_once(suppress=True))
    assert api.runs_calls == ["acme/api"]
    assert api.org_events_calls == ["acme"]
