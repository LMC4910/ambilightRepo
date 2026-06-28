"""Tests for the GitHub OAuth device flow (httpx mocked, no network)."""

import asyncio

import pytest

httpx = pytest.importorskip("httpx")

from ambilight.integrations.github import oauth


def _mock_httpx(monkeypatch, handler):
    """Route every httpx.AsyncClient request through *handler* (a MockTransport)."""
    orig = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return orig(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_request_device_code(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/login/device/code")
        return httpx.Response(200, json={
            "device_code": "DC", "user_code": "WXYZ-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900, "interval": 5,
        })

    _mock_httpx(monkeypatch, handler)
    data = asyncio.run(oauth.request_device_code("client123"))
    assert data["user_code"] == "WXYZ-1234"
    assert data["device_code"] == "DC"


def test_poll_for_token_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"access_token": "gho_abc", "token_type": "bearer"})

    _mock_httpx(monkeypatch, handler)
    tok = asyncio.run(oauth.poll_for_token("client123", "DC"))
    assert tok["access_token"] == "gho_abc"


def test_poll_for_token_pending(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"error": "authorization_pending"})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(oauth.DeviceFlowPending):
        asyncio.run(oauth.poll_for_token("client123", "DC"))


def test_poll_for_token_slow_down(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"error": "slow_down", "interval": 10})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(oauth.DeviceFlowSlowDown) as excinfo:
        asyncio.run(oauth.poll_for_token("client123", "DC"))
    assert excinfo.value.interval == 10


def test_poll_for_token_terminal_error(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"error": "expired_token",
                                         "error_description": "device code expired"})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(oauth.DeviceFlowError):
        asyncio.run(oauth.poll_for_token("client123", "DC"))
