"""Tests for the webhook-management REST methods added to GithubApi.

A fake httpx client records the request the method builds (method, path, JSON
body) so we can assert the GitHub hook API is called correctly — no network.
"""

import asyncio

from ambilight.integrations.github import api as api_mod
from ambilight.integrations.github.api import DEFAULT_HOOK_EVENTS, GithubApi


class FakeHttpResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.content = b"{}" if data is not None else b""

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def request(self, method, url, headers=None, params=None, json=None):
        self.calls.append({"method": method, "url": url, "json": json, "params": params})
        return self.response

    async def aclose(self):
        pass


def _api(response):
    api = GithubApi(lambda: "tok")
    api._client = FakeClient(response)   # bypass real httpx
    return api, api._client


def test_create_repo_hook_builds_correct_request():
    api, client = _api(FakeHttpResponse(201, {"id": 42}))
    out = asyncio.run(api.create_repo_hook(
        "acme/api", "https://abc.trycloudflare.com/api/github/webhook", "sek"))
    assert out == {"id": 42}
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/repos/acme/api/hooks")
    body = call["json"]
    assert body["config"]["url"].endswith("/api/github/webhook")
    assert body["config"]["content_type"] == "json"
    assert body["config"]["secret"] == "sek"
    assert body["events"] == DEFAULT_HOOK_EVENTS
    assert body["active"] is True


def test_update_repo_hook_uses_patch_and_id():
    api, client = _api(FakeHttpResponse(200, {"id": 7}))
    asyncio.run(api.update_repo_hook("acme/api", 7, "https://x/api/github/webhook", "sek"))
    call = client.calls[0]
    assert call["method"] == "PATCH"
    assert call["url"].endswith("/repos/acme/api/hooks/7")


def test_delete_repo_hook_uses_delete_and_no_body():
    api, client = _api(FakeHttpResponse(204, None))   # 204: no content
    out = asyncio.run(api.delete_repo_hook("acme/api", 9))
    assert out is None
    call = client.calls[0]
    assert call["method"] == "DELETE"
    assert call["url"].endswith("/repos/acme/api/hooks/9")


def test_get_repo_returns_permissions():
    api, _ = _api(FakeHttpResponse(200, {"permissions": {"admin": True}}))
    info = asyncio.run(api.get_repo("acme/api"))
    assert info["permissions"]["admin"] is True


def test_org_hook_endpoints():
    api, client = _api(FakeHttpResponse(201, {"id": 5}))
    asyncio.run(api.create_org_hook("acme", "https://x/api/github/webhook", "sek"))
    assert client.calls[0]["url"].endswith("/orgs/acme/hooks")
    assert client.calls[0]["method"] == "POST"


def test_error_status_raises():
    api, _ = _api(FakeHttpResponse(403, {"message": "Forbidden"}))
    try:
        asyncio.run(api.create_repo_hook("acme/api", "https://x/api/github/webhook", "sek"))
        assert False, "expected GithubApiError"
    except api_mod.GithubApiError as exc:
        assert exc.status == 403
