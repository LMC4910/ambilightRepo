"""Tests for webhook activation: tunnel + auto-registration + coverage wiring.

Uses a fake tunnel (no cloudflared process) and a fake API (no network) so the
orchestration in service._activate_webhooks is exercised hermetically.
"""

import asyncio

from ambilight.config import AppConfig, ConfigManager, DEFAULT_GITHUB_RULES_VERSION
from ambilight.integrations.github import service
from ambilight.integrations.github.service import GithubIntegration
from ambilight.integrations.github.store import GithubStore


class FakeController:
    def flash(self, *a, **k):
        pass


def _cfg(**gh):
    cfg = AppConfig()
    cfg.github.enabled = True
    cfg.github.rules_seeded = True
    cfg.github.rules_version = DEFAULT_GITHUB_RULES_VERSION
    for k, v in gh.items():
        setattr(cfg.github, k, v)
    ConfigManager._normalize_and_validate(cfg)
    return cfg


def _integration(cfg, store_path):
    gi = GithubIntegration(cfg, FakeController(), loop=None)
    gi._store = GithubStore(path=store_path)
    return gi


class FakeTunnel:
    def __init__(self, **kw):
        self.error = ""
        self.public_url = ""
        self.stopped = False

    async def start(self, timeout=30.0):
        self.public_url = "https://abc-123.trycloudflare.com"
        return self.public_url

    async def stop(self):
        self.stopped = True


class FakeTunnelNoUrl(FakeTunnel):
    async def start(self, timeout=30.0):
        self.error = "cloudflared not found"
        return None


class FakeHooksApi:
    def __init__(self, admin, existing=None):
        self.admin = admin
        self.existing = existing or {}     # repo -> [hook dicts]
        self.created = []
        self.updated = []
        self.deleted = []

    async def get_repo(self, repo):
        return {"permissions": {"admin": self.admin.get(repo, False)}}

    async def list_repo_hooks(self, repo):
        return self.existing.get(repo, [])

    async def create_repo_hook(self, repo, url, secret, events=None, active=True):
        self.created.append((repo, url))
        return {"id": 1000 + len(self.created)}

    async def update_repo_hook(self, repo, hook_id, url, secret, events=None, active=True):
        self.updated.append((repo, hook_id, url))
        return {"id": hook_id}

    async def delete_repo_hook(self, repo, hook_id):
        self.deleted.append((repo, hook_id))


def _patch(monkeypatch, tunnel_cls):
    # Don't touch the real OS keyring; pretend a secret already exists.
    monkeypatch.setattr(service.secrets_store, "get_secret", lambda k: "sek")
    monkeypatch.setattr(service, "CloudflaredTunnel", tunnel_cls)


def test_activate_registers_admin_repo_and_skips_non_admin(tmp_path, monkeypatch):
    _patch(monkeypatch, FakeTunnel)
    cfg = _cfg(watched_repos=["acme/api", "ext/lib"])
    gi = _integration(cfg, tmp_path / "g.db")
    gi._api = FakeHooksApi(admin={"acme/api": True, "ext/lib": False})

    status = asyncio.run(gi._activate_webhooks())

    assert gi._covered_repos == {"acme/api"}
    assert status["hook_status"]["acme/api"] == "registered"
    assert status["hook_status"]["ext/lib"] == "needs-admin"
    assert status["webhook_active"] is True
    assert status["tunnel_public_url"].endswith("trycloudflare.com")
    # The hook URL points at our receiver path on the tunnel host.
    assert gi._api.created == [("acme/api", "https://abc-123.trycloudflare.com/api/github/webhook")]


def test_activate_updates_existing_hook_instead_of_duplicating(tmp_path, monkeypatch):
    _patch(monkeypatch, FakeTunnel)
    cfg = _cfg(watched_repos=["acme/api"])
    gi = _integration(cfg, tmp_path / "g.db")
    # A prior hook (old tunnel host) is matched by the /api/github/webhook suffix.
    existing = {"acme/api": [{"id": 55, "config": {"url": "https://old.trycloudflare.com/api/github/webhook"}}]}
    gi._api = FakeHooksApi(admin={"acme/api": True}, existing=existing)

    asyncio.run(gi._activate_webhooks())

    assert gi._api.created == []                       # no duplicate
    assert gi._api.updated == [("acme/api", 55, "https://abc-123.trycloudflare.com/api/github/webhook")]


def test_activate_without_tunnel_url_falls_back_to_polling(tmp_path, monkeypatch):
    _patch(monkeypatch, FakeTunnelNoUrl)
    cfg = _cfg(watched_repos=["acme/api"])
    gi = _integration(cfg, tmp_path / "g.db")
    gi._api = FakeHooksApi(admin={"acme/api": True})

    status = asyncio.run(gi._activate_webhooks())

    assert gi._covered_repos == set()                  # nothing covered → full polling
    assert status["webhook_active"] is False
    assert status["tunnel_error"]
    assert gi._api.created == []                        # never tried to register


def test_disable_deletes_hooks_and_resumes_polling(tmp_path, monkeypatch):
    _patch(monkeypatch, FakeTunnel)
    cfg = _cfg(watched_repos=["acme/api"])
    gi = _integration(cfg, tmp_path / "g.db")
    gi._api = FakeHooksApi(admin={"acme/api": True})

    asyncio.run(gi._activate_webhooks())
    assert gi._covered_repos == {"acme/api"}

    asyncio.run(gi.disable_webhooks())
    assert gi._covered_repos == set()
    assert gi._api.deleted == [("acme/api", 1001)]      # the hook we created
    assert gi.status()["webhook_active"] is False


def test_find_our_hook_matching():
    f = GithubIntegration._find_our_hook
    hooks = [
        {"id": 1, "config": {"url": "https://other.example/somewhere"}},
        {"id": 2, "config": {"url": "https://x.trycloudflare.com/api/github/webhook"}},
    ]
    assert f(hooks, None) == 2                  # matched by path suffix
    assert f(hooks, 1) == 1                     # known id wins
    assert f([], None) is None                  # nothing to match
