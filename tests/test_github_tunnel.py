"""Tests for the cloudflared tunnel helper — pure URL parsing + argv building.

The process-spawning paths aren't exercised here (they need a real binary);
:func:`parse_public_url` and the argv builder hold the logic worth pinning.
"""

from ambilight.integrations.github import tunnel
from ambilight.integrations.github.tunnel import CloudflaredTunnel, parse_public_url


def test_parse_public_url_extracts_trycloudflare():
    line = "2026-06-29T00:00:00Z INF |  https://calm-frog-1234.trycloudflare.com  |"
    assert parse_public_url(line) == "https://calm-frog-1234.trycloudflare.com"


def test_parse_public_url_case_insensitive_and_hyphens():
    assert parse_public_url("Visit https://Big-Red-Box-9.trycloudflare.com now") == \
        "https://Big-Red-Box-9.trycloudflare.com"


def test_parse_public_url_none_when_absent():
    assert parse_public_url("just some log line") is None
    assert parse_public_url("") is None
    # A non-trycloudflare https URL must not match (we only trust the quick host).
    assert parse_public_url("https://example.com/api/github/webhook") is None


def test_locate_prefers_explicit_binary_override():
    t = CloudflaredTunnel(binary="/opt/cloudflared")
    assert t._binary == "/opt/cloudflared"


def test_build_argv_quick_tunnel():
    t = CloudflaredTunnel(local_url="http://127.0.0.1:7826")
    argv = t._build_argv("cf")
    assert argv == ["cf", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:7826"]


def test_build_argv_named_tunnel_uses_token():
    t = CloudflaredTunnel(named=True, hostname="ambi.example.com", token="tok123")
    argv = t._build_argv("cf")
    assert "run" in argv and "--token" in argv and "tok123" in argv
    assert "--url" not in argv


def test_named_mode_requires_token_and_hostname():
    assert CloudflaredTunnel(named=True, hostname="h", token="t")._named_mode is True
    assert CloudflaredTunnel(named=True, hostname="", token="t")._named_mode is False
    assert CloudflaredTunnel(named=True, hostname="h", token="")._named_mode is False
    assert CloudflaredTunnel(named=False, hostname="h", token="t")._named_mode is False


def test_build_argv_named_without_token_falls_back_to_quick():
    # Named requested but no token → not truly named mode → quick-tunnel argv, so
    # we never publish a hostname cloudflared was never told to serve.
    t = CloudflaredTunnel(local_url="http://127.0.0.1:7826", named=True,
                          hostname="ambi.example.com", token="")
    assert t._named_mode is False
    assert t._build_argv("cf") == ["cf", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:7826"]


def test_locate_cloudflared_returns_none_without_binary(monkeypatch):
    # No bundled binary, nothing on PATH → None (caller falls back to polling).
    monkeypatch.setattr(tunnel, "resource_path", lambda name: "/nonexistent/" + name)
    monkeypatch.setattr(tunnel.shutil, "which", lambda name: None)
    assert tunnel.locate_cloudflared() is None
