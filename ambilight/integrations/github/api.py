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
                       params: Optional[Dict[str, Any]] = None) -> Response:
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

        resp = await client.request(method, url, headers=headers, params=params)
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
