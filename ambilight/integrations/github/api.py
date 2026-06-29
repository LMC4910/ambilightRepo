"""
GitHub integration — async REST client
======================================
A thin async wrapper over GitHub's REST API built on ``httpx``. ``httpx`` is an
**optional** dependency (like ``paho-mqtt`` for the MQTT bridge): if it's absent
the whole GitHub integration stays disabled and the rest of the app is
unaffected — see :func:`httpx_available`.

The client supports conditional requests (``ETag`` / ``If-Modified-Since``) so
polling a feed that hasn't changed returns ``304`` and doesn't burn the hourly
rate limit, and it surfaces the ``X-RateLimit-*`` / ``X-Poll-Interval`` headers
the poller uses to pace itself.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
WEB_BASE = "https://github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"

# Webhook event names to subscribe a created hook to. These mirror the keys the
# normalizer understands (see normalize._WEBHOOK_TYPE) so every delivery maps to
# a known event_type. Note: starring fires the ``watch`` event (there is no
# ``star`` webhook), and the alert events only deliver where the feature is on.
DEFAULT_HOOK_EVENTS = [
    "push", "pull_request", "pull_request_review", "pull_request_review_comment",
    "issues", "issue_comment", "release", "create", "delete", "fork", "watch",
    "workflow_run", "check_suite", "check_run", "workflow_job",
    "deployment", "deployment_status", "discussion", "discussion_comment",
    "commit_comment", "dependabot_alert", "code_scanning_alert",
    "secret_scanning_alert",
]


def httpx_available() -> bool:
    """True when the optional ``httpx`` dependency can be imported."""
    try:
        import httpx  # noqa: F401
        return True
    except Exception:
        return False


class GithubApiError(Exception):
    """Raised for non-success, non-304 API responses."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


class Response:
    """Minimal normalized response (status + parsed json + relevant headers)."""

    __slots__ = ("status", "data", "etag", "last_modified", "poll_interval",
                 "rate_remaining", "rate_limit", "not_modified")

    def __init__(self, status: int, data: Any, headers: Dict[str, str]) -> None:
        self.status = status
        self.data = data
        self.not_modified = status == 304
        self.etag = headers.get("etag")
        self.last_modified = headers.get("last-modified")
        try:
            self.poll_interval = int(headers.get("x-poll-interval", "0") or 0)
        except ValueError:
            self.poll_interval = 0
        try:
            self.rate_remaining = int(headers.get("x-ratelimit-remaining", "-1"))
        except ValueError:
            self.rate_remaining = -1
        try:
            self.rate_limit = int(headers.get("x-ratelimit-limit", "-1"))
        except ValueError:
            self.rate_limit = -1


class GithubApi:
    def __init__(self, token_provider: Callable[[], str], timeout: float = 15.0) -> None:
        self._token_provider = token_provider
        self._timeout = timeout
        self._client = None  # lazily created httpx.AsyncClient

    def _ensure_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def _request(self, method: str, path: str, *,
                       etag: Optional[str] = None,
                       last_modified: Optional[str] = None,
                       params: Optional[Dict[str, Any]] = None,
                       json_body: Optional[Dict[str, Any]] = None) -> Response:
        client = self._ensure_client()
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        headers = {
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "Ambilight-Desktop",
        }
        token = self._token_provider() or ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if etag:
            headers["If-None-Match"] = etag
        elif last_modified:
            headers["If-Modified-Since"] = last_modified

        resp = await client.request(method, url, headers=headers, params=params, json=json_body)
        data: Any = None
        if resp.status_code not in (304,) and resp.content:
            try:
                data = resp.json()
            except Exception:
                data = None
        out = Response(resp.status_code, data, {k.lower(): v for k, v in resp.headers.items()})
        if resp.status_code >= 400:
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("message", ""))
            raise GithubApiError(resp.status_code, msg)
        return out

    # --- identity --------------------------------------------------------
    async def get_user(self) -> Dict[str, Any]:
        return (await self._request("GET", "/user")).data or {}

    async def get_user_orgs(self) -> List[Dict[str, Any]]:
        return (await self._request("GET", "/user/orgs", params={"per_page": 100})).data or []

    async def get_user_repos(self, per_page: int = 100) -> List[Dict[str, Any]]:
        return (await self._request(
            "GET", "/user/repos",
            params={"per_page": per_page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
        )).data or []

    async def get_repo_workflows(self, repo: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """List a repo's Actions workflows. ``name`` matches a run's workflow name
        (see :func:`normalize.normalize_workflow_run`), so the UI can offer it as a
        picker instead of having the user type it."""
        data = (await self._request(
            "GET", f"/repos/{repo}/actions/workflows", params={"per_page": per_page},
        )).data or {}
        return data.get("workflows", []) if isinstance(data, dict) else []

    # --- pollable feeds (conditional) -----------------------------------
    async def get_notifications(self, etag: Optional[str] = None,
                                last_modified: Optional[str] = None,
                                all_: bool = False) -> Response:
        return await self._request(
            "GET", "/notifications", etag=etag, last_modified=last_modified,
            params={"all": "true" if all_ else "false", "per_page": 50},
        )

    async def get_workflow_runs(self, repo: str, etag: Optional[str] = None,
                                per_page: int = 20) -> Response:
        return await self._request(
            "GET", f"/repos/{repo}/actions/runs", etag=etag,
            params={"per_page": per_page},
        )

    async def get_repo_events(self, repo: str, etag: Optional[str] = None) -> Response:
        return await self._request(
            "GET", f"/repos/{repo}/events", etag=etag, params={"per_page": 30},
        )

    async def get_org_events(self, org: str, etag: Optional[str] = None) -> Response:
        return await self._request(
            "GET", f"/orgs/{org}/events", etag=etag, params={"per_page": 30},
        )

    # --- repository identity / permissions ------------------------------
    async def get_repo(self, repo: str) -> Dict[str, Any]:
        """Fetch a repo object. ``permissions.admin`` tells us whether the token
        can register a webhook on it (only repo admins can)."""
        return (await self._request("GET", f"/repos/{repo}")).data or {}

    # --- webhook management (push delivery; needs admin on the repo) ------
    async def list_repo_hooks(self, repo: str) -> List[Dict[str, Any]]:
        return (await self._request(
            "GET", f"/repos/{repo}/hooks", params={"per_page": 100},
        )).data or []

    async def create_repo_hook(self, repo: str, url: str, secret: str,
                               events: Optional[List[str]] = None,
                               active: bool = True) -> Dict[str, Any]:
        body = {
            "name": "web",
            "active": bool(active),
            "events": list(events or DEFAULT_HOOK_EVENTS),
            "config": {
                "url": url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        return (await self._request("POST", f"/repos/{repo}/hooks", json_body=body)).data or {}

    async def update_repo_hook(self, repo: str, hook_id: int, url: str, secret: str,
                               events: Optional[List[str]] = None,
                               active: bool = True) -> Dict[str, Any]:
        body = {
            "active": bool(active),
            "events": list(events or DEFAULT_HOOK_EVENTS),
            "config": {
                "url": url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        return (await self._request(
            "PATCH", f"/repos/{repo}/hooks/{hook_id}", json_body=body,
        )).data or {}

    async def delete_repo_hook(self, repo: str, hook_id: int) -> None:
        await self._request("DELETE", f"/repos/{repo}/hooks/{hook_id}")

    # --- org webhook management (needs the admin:org_hook scope) ----------
    async def list_org_hooks(self, org: str) -> List[Dict[str, Any]]:
        return (await self._request(
            "GET", f"/orgs/{org}/hooks", params={"per_page": 100},
        )).data or []

    async def create_org_hook(self, org: str, url: str, secret: str,
                              events: Optional[List[str]] = None,
                              active: bool = True) -> Dict[str, Any]:
        body = {
            "name": "web",
            "active": bool(active),
            "events": list(events or DEFAULT_HOOK_EVENTS),
            "config": {
                "url": url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        return (await self._request("POST", f"/orgs/{org}/hooks", json_body=body)).data or {}

    async def update_org_hook(self, org: str, hook_id: int, url: str, secret: str,
                              events: Optional[List[str]] = None,
                              active: bool = True) -> Dict[str, Any]:
        body = {
            "active": bool(active),
            "events": list(events or DEFAULT_HOOK_EVENTS),
            "config": {
                "url": url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        return (await self._request(
            "PATCH", f"/orgs/{org}/hooks/{hook_id}", json_body=body,
        )).data or {}

    async def delete_org_hook(self, org: str, hook_id: int) -> None:
        await self._request("DELETE", f"/orgs/{org}/hooks/{hook_id}")
