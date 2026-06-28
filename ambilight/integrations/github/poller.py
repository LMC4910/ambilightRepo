"""
GitHub integration — polling loop
=================================
The desktop app sits behind NAT, so instead of receiving webhooks it *polls*
GitHub. One async loop fans out across the complementary sources that together
cover "anything GitHub can tell you about":

* the **notifications inbox** (``/notifications``) — mentions, review requests,
  assignments, CI activity you're subscribed to, ...
* **Actions workflow runs** per watched repo — granular CI success/failure;
* the **events feed** for watched repos / orgs — pushes, PRs, issues, releases.

Every request is conditional (``ETag`` cursor from the store), so an unchanged
feed returns ``304`` and costs no rate limit. The loop honours GitHub's
``X-Poll-Interval`` and backs off on errors. Each genuinely-new, de-duplicated
event is handed to the ``on_event`` callback (the service, which maps it to a
flash). The loop never touches LEDs directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, List

from .api import GithubApi, GithubApiError
from .health import GithubHealth
from . import normalize
from .models import GithubEvent
from .store import GithubStore

logger = logging.getLogger(__name__)

OnEvent = Callable[[GithubEvent], Awaitable[None]]


class GithubPoller:
    def __init__(self, api: GithubApi, store: GithubStore, health: GithubHealth,
                 on_event: OnEvent, account: str = "") -> None:
        self._api = api
        self._store = store
        self._health = health
        self._on_event = on_event
        self.account = account
        # Config-driven knobs (set via configure()).
        self._base_interval = 60.0
        self._watch_notifications = True
        self._watched_repos: List[str] = []
        self._watched_orgs: List[str] = []
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._error_backoff = 0.0

    def configure(self, *, base_interval: float, watch_notifications: bool,
                  watched_repos: List[str], watched_orgs: List[str]) -> None:
        self._base_interval = max(15.0, float(base_interval))
        self._watch_notifications = bool(watch_notifications)
        self._watched_repos = [r for r in (watched_repos or []) if r]
        self._watched_orgs = [o for o in (watched_orgs or []) if o]
        self._health.watched_repos = len(self._watched_repos)

    # --- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="github-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # --- main loop -------------------------------------------------------
    async def _run(self) -> None:
        logger.info("[GitHub] Poller started (account=%s, repos=%d).",
                    self.account, len(self._watched_repos))
        # First pass primes the de-dup cursor without flashing the whole backlog.
        first_pass = True
        while not self._stop.is_set():
            poll_interval = self._base_interval
            try:
                hinted = await self._poll_once(suppress=first_pass)
                poll_interval = max(self._base_interval, hinted)
                self._error_backoff = 0.0
                first_pass = False
            except GithubApiError as exc:
                self._health.record_error(str(exc))
                if exc.status in (401, 403):
                    # Auth/rate problem — back off hard so we don't hammer it.
                    poll_interval = max(poll_interval, 120.0)
                self._error_backoff = min(300.0, (self._error_backoff or 30.0) * 1.5)
                poll_interval = max(poll_interval, self._error_backoff)
                logger.warning("[GitHub] Poll error (%s); backing off %.0fs.", exc, poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                self._health.record_error(str(exc))
                self._error_backoff = min(300.0, (self._error_backoff or 30.0) * 1.5)
                poll_interval = max(poll_interval, self._error_backoff)
                logger.warning("[GitHub] Unexpected poll error (%s); backing off %.0fs.",
                               exc, poll_interval)

            self._health.poll_interval_s = poll_interval
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
        logger.info("[GitHub] Poller stopped.")

    async def _poll_once(self, suppress: bool) -> float:
        """Run one poll cycle across all sources. Returns a poll-interval hint."""
        import time as _time

        hint = 0.0
        events: List[GithubEvent] = []

        if self._watch_notifications:
            hint = max(hint, await self._poll_notifications(events))
        for repo in self._watched_repos:
            await self._poll_workflow_runs(repo, events)
            await self._poll_repo_events(repo, events)
        for org in self._watched_orgs:
            await self._poll_org_events(org, events)

        self._health.last_poll_ts = _time.time()

        # De-dup and dispatch (oldest first so the flash order matches reality).
        events.sort(key=lambda e: e.timestamp)
        for ev in events:
            if not self._store.mark_seen(ev.id):
                continue
            self._store.add_event(ev)
            self._health.last_event_ts = ev.timestamp
            if not suppress:
                await self._on_event(ev)
        return hint

    # --- per-source helpers ---------------------------------------------
    async def _poll_notifications(self, out: List[GithubEvent]) -> float:
        key = "notifications"
        state = self._store.get_poll_state(key)
        resp = await self._api.get_notifications(etag=state.get("etag"),
                                                 last_modified=state.get("last_modified"))
        self._update_rate(resp)
        if resp.not_modified:
            return float(resp.poll_interval)
        self._store.set_poll_state(key, etag=resp.etag, last_modified=resp.last_modified)
        for item in (resp.data or []):
            out.append(normalize.normalize_notification(item, self.account))
        return float(resp.poll_interval)

    async def _poll_workflow_runs(self, repo: str, out: List[GithubEvent]) -> None:
        key = f"runs:{repo}"
        state = self._store.get_poll_state(key)
        resp = await self._api.get_workflow_runs(repo, etag=state.get("etag"))
        self._update_rate(resp)
        if resp.not_modified:
            return
        self._store.set_poll_state(key, etag=resp.etag)
        runs = (resp.data or {}).get("workflow_runs", []) if isinstance(resp.data, dict) else []
        for run in runs:
            out.append(normalize.normalize_workflow_run(run, self.account, repository=repo))

    async def _poll_repo_events(self, repo: str, out: List[GithubEvent]) -> None:
        key = f"events:{repo}"
        state = self._store.get_poll_state(key)
        resp = await self._api.get_repo_events(repo, etag=state.get("etag"))
        self._update_rate(resp)
        if resp.not_modified:
            return
        self._store.set_poll_state(key, etag=resp.etag)
        for ev in (resp.data or []):
            out.append(normalize.normalize_event(ev, self.account))

    async def _poll_org_events(self, org: str, out: List[GithubEvent]) -> None:
        key = f"orgevents:{org}"
        state = self._store.get_poll_state(key)
        resp = await self._api.get_org_events(org, etag=state.get("etag"))
        self._update_rate(resp)
        if resp.not_modified:
            return
        self._store.set_poll_state(key, etag=resp.etag)
        for ev in (resp.data or []):
            out.append(normalize.normalize_event(ev, self.account))

    def _update_rate(self, resp) -> None:
        if resp.rate_remaining >= 0:
            self._health.rate_remaining = resp.rate_remaining
        if resp.rate_limit >= 0:
            self._health.rate_limit = resp.rate_limit
