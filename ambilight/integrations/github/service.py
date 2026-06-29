"""
GitHub integration — service / orchestrator
===========================================
``GithubIntegration`` is the public entry point. It mirrors
:class:`NotificationFlashService`'s lifecycle (created at startup, refreshed on
``CONFIG_UPDATE``) and ties the pieces together:

    OAuth device flow ─▶ token (keyring)
                              │
            poller ──▶ normalize ──▶ store (de-dup) ──▶ mapper ──▶ controller.flash
                                                          │
                                                          └▶ bus.publish("GITHUB_EVENT")

It never drives LEDs directly — it resolves a colour/pattern from the user's
rules and hands the final flash to the pipeline, exactly like the notification
flash service. The whole integration is off by default and degrades to a no-op
when the optional ``httpx`` dependency is missing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import secrets as _secrets

from ...events import bus
from .. import secrets_store
from . import api as api_mod
from . import mapper, oauth
from . import webhook as webhook_mod
from .health import (
    AUTH_CONNECTED,
    AUTH_DISCONNECTED,
    AUTH_PENDING,
    GithubHealth,
)
from .models import GithubEvent
from .poller import GithubPoller
from .store import GithubStore
from .tunnel import CloudflaredTunnel

# Cache key (in the SQLite `cache` table) for the {repo_or_org: hook_id} map of
# hooks we created, so we can update them in place (idempotent) and delete them
# on disable instead of leaking duplicates.
_HOOKS_CACHE_KEY = "webhook_hooks"
# The receiver path the tunnel fronts.
_WEBHOOK_PATH = "/api/github/webhook"
# A unique ownership marker appended as a query param to our callback URL. We
# match existing hooks by this tag (not the generic receiver path), so we never
# adopt — and so on disable never delete — a webhook some *other* tool registered
# at the same /api/github/webhook path. Query params are ignored by the receiver's
# routing and excluded from the HMAC (which signs the body), so the tag is purely
# an identity marker and does not affect delivery or verification.
_WEBHOOK_OWNER_TAG = "ambilight-leds"


def _build_delivery_url(public_url: str) -> str:
    """Our callback URL: the receiver path plus the ownership marker query param."""
    return f"{public_url}{_WEBHOOK_PATH}?app={_WEBHOOK_OWNER_TAG}"

logger = logging.getLogger(__name__)

# The app's own GitHub OAuth App client id, shipped as the built-in default so
# "Connect" works out of the box with no setup. A device-flow client id is NOT a
# secret — it ships in the app and the flow uses no client secret — so baking it
# in is the standard practice for desktop OAuth apps. Override it (e.g. to test
# against your own OAuth App) via config, the AMBILIGHT_GITHUB_CLIENT_ID env var,
# a .env file, or a build-baked github_client_id.txt — see resolve_client_id().
BUILTIN_CLIENT_ID = "Ov23liaWLuf6hK0eJIIE"


def resolve_client_id() -> str:
    """Resolve the GitHub OAuth App client id.

    A device-flow client id is **not a secret** (it ships in the app). Resolution
    order, first match wins:

    1. ``AMBILIGHT_GITHUB_CLIENT_ID`` env var — including values loaded from a
       ``.env`` file at startup (see ``paths.load_env_files``).
    2. A build-baked ``github_client_id.txt`` bundled with the frozen app (CI can
       inject it from a repo secret/variable at release time via ``build.py``).
    3. The built-in :data:`BUILTIN_CLIENT_ID` default, so the integration works
       without any configuration.

    The per-user config's ``github.client_id`` overrides all of these (handled by
    the caller).
    """
    v = os.environ.get("AMBILIGHT_GITHUB_CLIENT_ID", "").strip()
    if v:
        return v
    try:
        from ...paths import resource_path
        p = resource_path("github_client_id.txt")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                baked = fh.read().strip()
            if baked:
                return baked
    except Exception:
        pass
    return BUILTIN_CLIENT_ID


class GithubIntegration:
    def __init__(self, cfg, controller, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._controller = controller
        self._loop = loop
        self._gh = getattr(cfg, "github", None)
        self._health = GithubHealth()
        self._health.httpx_available = api_mod.httpx_available()
        self._store: Optional[GithubStore] = None
        self._api: Optional[api_mod.GithubApi] = None
        self._poller: Optional[GithubPoller] = None
        self._auth_task: Optional[asyncio.Task] = None
        # Webhook (event-driven) delivery path.
        self._tunnel: Optional[CloudflaredTunnel] = None
        self._covered_repos: set[str] = set()   # repos served by a live webhook
        self._covered_orgs: set[str] = set()     # orgs served by a live webhook
        # Serialises hook (re)registration so the initial activation and a
        # tunnel-URL-change reconcile can't run _register_all_hooks concurrently.
        self._hook_lock = asyncio.Lock()
        self.account = ""
        self._apply_config(cfg)

    # --- config / knobs --------------------------------------------------
    def _apply_config(self, cfg) -> None:
        self._gh = getattr(cfg, "github", None)
        self._health.enabled = bool(self._gh and getattr(self._gh, "enabled", False))

    @property
    def _client_id(self) -> str:
        return (getattr(self._gh, "client_id", "") or resolve_client_id() or "").strip()

    @property
    def _scopes(self):
        scopes = getattr(self._gh, "scopes", None) if self._gh else None
        return tuple(scopes) if scopes else oauth.DEFAULT_SCOPES

    def _ensure_store(self) -> GithubStore:
        if self._store is None:
            self._store = GithubStore()
        return self._store

    def _default_pattern(self) -> Dict[str, Any]:
        gh = self._gh
        return {
            "blink_count": int(getattr(gh, "blink_count", 2)),
            "on_ms": int(getattr(gh, "on_ms", 180)),
            "off_ms": int(getattr(gh, "off_ms", 120)),
            "brightness": float(getattr(gh, "brightness", 1.0)),
        }

    # --- lifecycle (mirrors NotificationFlashService) --------------------
    def start(self) -> None:
        self._health.httpx_available = api_mod.httpx_available()
        if not self._health.httpx_available:
            logger.info("[GitHub] httpx not installed; integration disabled.")
            return
        self._apply_running_state()

    def update_config(self, cfg) -> None:
        self._apply_config(cfg)
        if self._poller is not None:
            self._configure_poller()
        self._apply_running_state()

    def stop(self) -> None:
        if self._auth_task is not None:
            self._auth_task.cancel()
            self._auth_task = None
        if self._tunnel is not None:
            # Drop the tunnel process; leave remote hooks in place to be
            # re-pointed on next launch (quick-tunnel URLs change anyway).
            self._schedule(self._tunnel.stop())
            self._tunnel = None
            self._covered_repos.clear()
            self._covered_orgs.clear()
        if self._poller is not None:
            # Best-effort async teardown; on shutdown the loop may already be
            # winding down, so cancel the task directly too.
            self._schedule(self._poller.stop())
            self._poller = None
        if self._api is not None:
            self._schedule(self._api.close())
            self._api = None
        if self._store is not None:
            self._store.close()
            self._store = None

    # --- running-state reconciliation -----------------------------------
    def _apply_running_state(self) -> None:
        """Start or stop polling so it matches (enabled ∧ token ∧ httpx)."""
        enabled = self._health.enabled and self._health.httpx_available
        token = secrets_store.get_github_token()
        if enabled and token:
            if self._poller is None:
                self._schedule(self._connect())
        else:
            if self._poller is not None or self._api is not None:
                self._schedule(self._teardown_poller())
            if not token:
                self._health.auth_state = AUTH_DISCONNECTED

    async def _connect(self) -> None:
        if self._poller is not None:
            return
        token = secrets_store.get_github_token()
        if not token or not self._health.httpx_available:
            return
        store = self._ensure_store()
        self._api = api_mod.GithubApi(lambda: secrets_store.get_github_token())
        try:
            user = await self._api.get_user()
            self.account = str(user.get("login", "") or "")
            self._health.account = self.account
            store.set_cache("account", user)
        except Exception as exc:
            self._health.record_error(f"identity fetch failed: {exc}")
            logger.warning("[GitHub] Could not fetch identity: %s", exc)
        self._health.auth_state = AUTH_CONNECTED
        self._poller = GithubPoller(self._api, store, self._health, self._dispatch, self.account)
        self._configure_poller()
        self._poller.start()
        logger.info("[GitHub] Connected as %s; polling started.", self.account or "?")
        # Event-driven delivery: if the user turned webhooks on, bring up the
        # tunnel and (re)register hooks now. Quick-tunnel URLs change per launch,
        # so this re-points existing hooks on every connect. Best-effort — any
        # failure just leaves the affected repos on polling.
        if bool(getattr(self._gh, "webhook_enabled", False)):
            try:
                await self._activate_webhooks()
            except Exception as exc:  # pragma: no cover - defensive
                self._health.record_error(f"webhook enable failed: {exc}")
                logger.warning("[GitHub] Webhook enable failed; staying on polling: %s", exc)

    def _configure_poller(self) -> None:
        if self._poller is None or self._gh is None:
            return
        self._poller.configure(
            base_interval=float(getattr(self._gh, "poll_interval_s", 60.0)),
            watch_notifications=bool(getattr(self._gh, "watch_notifications", True)),
            watched_repos=list(getattr(self._gh, "watched_repos", []) or []),
            watched_orgs=list(getattr(self._gh, "watched_orgs", []) or []),
            covered_repos=set(self._covered_repos),
            covered_orgs=set(self._covered_orgs),
        )

    async def _teardown_poller(self) -> None:
        # Webhooks ride on the same connection — drop the tunnel too (runtime only;
        # remote hooks are left in place to be re-pointed on the next connect).
        await self._teardown_webhooks_runtime()
        if self._poller is not None:
            await self._poller.stop()
            self._poller = None
        if self._api is not None:
            await self._api.close()
            self._api = None

    # --- event dispatch (poller → lights) --------------------------------
    async def _dispatch(self, ev: GithubEvent) -> None:
        try:
            gh = self._gh
            if gh is None:
                logger.warning("[GitHub] dispatch skipped for %s/%s: github config missing", ev.event_type, ev.action)
                return
            rules = list(getattr(gh, "rules", []) or [])
            default_color = tuple(getattr(gh, "default_color", [88, 166, 255]))
            if not rules:
                logger.debug("[GitHub] no rules configured; falling back to default color for %s/%s", ev.event_type, ev.action)
            resolved = mapper.resolve(ev, rules, default_color, self._default_pattern())
            if resolved is not None:
                rgb, pattern = resolved
                self._controller.flash(list(rgb), pattern, label=f"GitHub: {ev.title}")
                logger.info("[GitHub] %s/%s in %s -> flash %s",
                            ev.event_type, ev.action, ev.repository or "-", rgb)
            await bus.publish("GITHUB_EVENT", ev.to_dict())
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[GitHub] dispatch failed: %s", exc)

    # --- webhook ingestion (optional/advanced path) ---------------------
    async def ingest_webhook(self, event_name: str, payload: Dict[str, Any],
                             delivery_id: str = "") -> None:
        """Normalise + de-dup + dispatch a webhook delivery (same path as polls)."""
        from . import normalize

        if delivery_id:
            payload = {**payload, "_delivery_id": delivery_id}
        ev = normalize.normalize_webhook(event_name, payload, self.account)
        self._health.last_delivery_ts = time.time()
        store = self._ensure_store()
        if not store.mark_seen(ev.id):
            return
        store.add_event(ev)
        self._health.last_event_ts = ev.timestamp
        await self._dispatch(ev)

    # --- webhook activation (tunnel + auto-registration) ----------------
    def _update_gh_config(self, **fields: Any) -> None:
        """Persist a partial github-config update and refresh the local view."""
        try:
            from ...config import ConfigManager
            ConfigManager.update({"github": fields})
            self._gh = ConfigManager.get().github
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[GitHub] could not persist config %s: %s", fields, exc)

    def _ensure_webhook_secret(self) -> str:
        """Return the shared HMAC secret, generating + persisting it on first use."""
        secret = secrets_store.get_secret(webhook_mod.WEBHOOK_SECRET_KEY)
        if not secret:
            secret = _secrets.token_hex(32)
            secrets_store.set_secret(webhook_mod.WEBHOOK_SECRET_KEY, secret)
            self._update_gh_config(webhook_secret_set=True)
        return secret

    async def enable_webhooks(self) -> Dict[str, Any]:
        """User action: turn webhooks on (persist the flag, connect, activate).

        Idempotent and safe to call repeatedly. The heavy lifting lives in
        :meth:`_activate_webhooks`; connecting auto-activates via that method, so
        we never run it twice. Returns a status dict.
        """
        if not self._health.httpx_available:
            raise RuntimeError("httpx is not installed; GitHub integration unavailable")
        self._update_gh_config(webhook_enabled=True)
        if self._api is None:
            # Connecting auto-activates webhooks now that the flag is set.
            await self._connect()
            if self._api is None:
                raise RuntimeError("not connected to GitHub")
            return self.status()
        return await self._activate_webhooks()

    async def _activate_webhooks(self) -> Dict[str, Any]:
        """Open the tunnel and (re)register hooks on each admin'd watched repo.

        Assumes the API client exists (called from a connected state). Repos we
        can't admin — and the notifications inbox — keep polling.
        """
        if self._api is None:
            return self.status()
        secret = self._ensure_webhook_secret()

        # 1. Bring up the public tunnel. The on_url_change callback re-points our
        # hooks if a quick tunnel restarts with a new hostname (see below).
        if self._tunnel is None:
            token = secrets_store.get_secret("github_tunnel_token") if getattr(self._gh, "tunnel_named", False) else ""
            self._tunnel = CloudflaredTunnel(
                local_url="http://127.0.0.1:7826",
                named=bool(getattr(self._gh, "tunnel_named", False)),
                hostname=str(getattr(self._gh, "tunnel_hostname", "") or ""),
                token=token,
                on_url_change=self._on_tunnel_url_changed,
            )
        public_url = await self._tunnel.start()
        self._health.tunnel_public_url = public_url or ""
        self._health.tunnel_running = bool(public_url)
        if not public_url:
            # No tunnel → no webhooks. Stay on full polling, surface the reason.
            self._health.tunnel_error = self._tunnel.error
            self._health.webhook_active = False
            self._covered_repos.clear()
            self._covered_orgs.clear()
            self._configure_poller()
            return self.status()
        self._health.tunnel_error = ""

        # 2. Register/update a hook per watched repo we administer.
        delivery_url = _build_delivery_url(public_url)
        async with self._hook_lock:
            await self._register_all_hooks(delivery_url, secret)

        self._health.webhook_active = bool(self._covered_repos or self._covered_orgs)
        self._configure_poller()
        logger.info("[GitHub] Webhooks active via %s (covered: %d repos, %d orgs).",
                    public_url, len(self._covered_repos), len(self._covered_orgs))
        return self.status()

    async def _on_tunnel_url_changed(self, new_url: str) -> None:
        """Re-point hooks after the tunnel comes back up on a new public URL.

        Quick-tunnel hostnames change across cloudflared restarts; without this,
        GitHub would keep POSTing to the dead URL. Fires only on a *changed* URL
        (not the first one — that path is handled by _activate_webhooks).
        """
        if not new_url or self._tunnel is None or self._api is None:
            return
        try:
            secret = self._ensure_webhook_secret()
            self._health.tunnel_public_url = new_url
            self._health.tunnel_running = True
            self._health.tunnel_error = ""
            delivery_url = _build_delivery_url(new_url)
            async with self._hook_lock:
                await self._register_all_hooks(delivery_url, secret)
            self._health.webhook_active = bool(self._covered_repos or self._covered_orgs)
            self._configure_poller()
            logger.info("[GitHub] Tunnel URL changed to %s; hooks re-registered.", new_url)
        except Exception as exc:  # pragma: no cover - defensive
            self._health.record_error(f"hook re-register after tunnel change: {exc}")
            logger.warning("[GitHub] Could not re-register hooks after tunnel change: %s", exc)

    async def _register_all_hooks(self, delivery_url: str, secret: str) -> None:
        store = self._ensure_store()
        hooks_map: Dict[str, int] = dict(store.get_cache(_HOOKS_CACHE_KEY) or {})
        self._covered_repos.clear()
        self._health.hook_status = {}

        watched_repos = list(getattr(self._gh, "watched_repos", []) or [])
        for repo in watched_repos:
            repo = str(repo).strip()
            if not repo:
                continue
            try:
                info = await self._api.get_repo(repo)
                if not bool((info.get("permissions") or {}).get("admin")):
                    self._health.hook_status[repo] = "needs-admin"
                    continue
                hook_id = await self._reconcile_repo_hook(repo, delivery_url, secret, hooks_map)
                hooks_map[repo.lower()] = hook_id
                self._covered_repos.add(repo.lower())
                self._health.hook_status[repo] = "registered"
            except api_mod.GithubApiError as exc:
                self._health.hook_status[repo] = "needs-admin" if exc.status in (403, 404) else "error"
                self._health.record_error(f"hook register {repo}: {exc}")
                logger.warning("[GitHub] Could not register webhook on %s: %s", repo, exc)
            except Exception as exc:  # pragma: no cover - defensive
                self._health.hook_status[repo] = "error"
                self._health.record_error(f"hook register {repo}: {exc}")

        # Org hooks (best-effort; needs the admin:org_hook scope).
        for org in list(getattr(self._gh, "watched_orgs", []) or []):
            org = str(org).strip()
            if not org:
                continue
            try:
                hook_id = await self._reconcile_org_hook(org, delivery_url, secret, hooks_map)
                hooks_map[f"org:{org.lower()}"] = hook_id
                self._covered_orgs.add(org.lower())
                self._health.hook_status[f"org:{org}"] = "registered"
            except api_mod.GithubApiError as exc:
                self._health.hook_status[f"org:{org}"] = "needs-admin" if exc.status in (403, 404) else "error"
                logger.warning("[GitHub] Could not register org webhook on %s: %s", org, exc)
            except Exception as exc:  # pragma: no cover - defensive
                self._health.hook_status[f"org:{org}"] = "error"

        store.set_cache(_HOOKS_CACHE_KEY, hooks_map)

    async def _reconcile_repo_hook(self, repo: str, delivery_url: str, secret: str,
                                   hooks_map: Dict[str, int]) -> int:
        """Create our hook on *repo*, or update the existing one in place. Returns its id."""
        existing = await self._api.list_repo_hooks(repo)
        hook_id = self._find_our_hook(existing, hooks_map.get(repo.lower()))
        if hook_id is not None:
            await self._api.update_repo_hook(repo, hook_id, delivery_url, secret)
            return hook_id
        created = await self._api.create_repo_hook(repo, delivery_url, secret)
        return int(created.get("id"))

    async def _reconcile_org_hook(self, org: str, delivery_url: str, secret: str,
                                  hooks_map: Dict[str, int]) -> int:
        existing = await self._api.list_org_hooks(org)
        hook_id = self._find_our_hook(existing, hooks_map.get(f"org:{org.lower()}"))
        if hook_id is not None:
            await self._api.update_org_hook(org, hook_id, delivery_url, secret)
            return hook_id
        created = await self._api.create_org_hook(org, delivery_url, secret)
        return int(created.get("id"))

    @staticmethod
    def _find_our_hook(existing: List[Dict[str, Any]], known_id: Optional[int]) -> Optional[int]:
        """Match a previously-created hook by id, else by our ownership marker.

        Quick-tunnel hostnames change each launch, so we can't match on the full
        URL. We match on the ``app=<owner-tag>`` query marker we always append —
        never the bare ``/api/github/webhook`` path, which another tool could also
        use — so we never adopt or delete a webhook we didn't create.
        """
        ids = {int(h.get("id")) for h in existing if h.get("id") is not None}
        if known_id is not None and int(known_id) in ids:
            return int(known_id)
        marker = f"app={_WEBHOOK_OWNER_TAG}"
        for h in existing:
            url = str((h.get("config") or {}).get("url", "") or "")
            if marker in url:
                return int(h.get("id"))
        return None

    async def _delete_remote_hooks(self) -> None:
        """Best-effort: delete every hook we created (needs a valid token)."""
        if self._api is None:
            return
        store = self._ensure_store()
        hooks_map: Dict[str, int] = dict(store.get_cache(_HOOKS_CACHE_KEY) or {})
        # Keep any entry whose delete failed so a transient API error doesn't leak
        # the remote hook *and* discard the only id we had to retry cleanup with.
        remaining: Dict[str, int] = {}
        for key, hook_id in list(hooks_map.items()):
            try:
                if key.startswith("org:"):
                    await self._api.delete_org_hook(key[4:], int(hook_id))
                else:
                    await self._api.delete_repo_hook(key, int(hook_id))
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                logger.debug("[GitHub] could not delete hook %s/%s: %s", key, hook_id, exc)
                remaining[key] = hook_id
        store.set_cache(_HOOKS_CACHE_KEY, remaining)

    async def _teardown_webhooks_runtime(self) -> None:
        """Stop the tunnel and clear runtime webhook state (no config change)."""
        if self._tunnel is not None:
            await self._tunnel.stop()
            self._tunnel = None
        self._covered_repos.clear()
        self._covered_orgs.clear()
        self._health.tunnel_running = False
        self._health.webhook_active = False
        self._health.tunnel_public_url = ""
        self._health.tunnel_error = ""
        self._health.hook_status = {}

    async def disable_webhooks(self) -> Dict[str, Any]:
        """User action: delete our hooks, drop the tunnel, and resume full polling."""
        self._update_gh_config(webhook_enabled=False)
        await self._delete_remote_hooks()
        await self._teardown_webhooks_runtime()
        self._configure_poller()
        logger.info("[GitHub] Webhooks disabled; polling resumed.")
        return self.status()

    # --- OAuth device flow ----------------------------------------------
    async def begin_auth(self) -> Dict[str, Any]:
        """Start the device flow; returns the user-facing prompt.

        Raises ValueError if no client id is configured.
        """
        if not self._health.httpx_available:
            raise RuntimeError("httpx is not installed; GitHub integration unavailable")
        client_id = self._client_id
        if not client_id:
            raise ValueError(
                "No GitHub OAuth client id configured. Set github.client_id "
                "(or the AMBILIGHT_GITHUB_CLIENT_ID env var)."
            )
        dc = await oauth.request_device_code(client_id, self._scopes)
        self._health.auth_state = AUTH_PENDING
        self._health.user_code = str(dc.get("user_code", ""))
        self._health.verification_uri = str(
            dc.get("verification_uri") or dc.get("verification_uri_complete") or
            "https://github.com/login/device"
        )
        expires_in = int(dc.get("expires_in", 900))
        self._health.auth_expires_at = time.time() + expires_in
        if self._auth_task is not None:
            self._auth_task.cancel()
        self._auth_task = asyncio.create_task(
            self._poll_device_flow(client_id, dc), name="github-device-flow"
        )
        return {
            "user_code": self._health.user_code,
            "verification_uri": self._health.verification_uri,
            "expires_in": expires_in,
            "interval": int(dc.get("interval", 5)),
        }

    async def _poll_device_flow(self, client_id: str, dc: Dict[str, Any]) -> None:
        device_code = str(dc.get("device_code", ""))
        interval = max(5, int(dc.get("interval", 5)))
        deadline = time.time() + int(dc.get("expires_in", 900))
        try:
            while time.time() < deadline:
                await asyncio.sleep(interval)
                try:
                    tok = await oauth.poll_for_token(client_id, device_code)
                except oauth.DeviceFlowPending:
                    continue
                except oauth.DeviceFlowSlowDown as slow:
                    interval = slow.interval + 1
                    continue
                except oauth.DeviceFlowError as err:
                    self._health.auth_state = AUTH_DISCONNECTED
                    self._health.record_error(f"auth failed: {err}")
                    logger.warning("[GitHub] Device flow failed: %s", err)
                    return
                # Success.
                secrets_store.set_github_token(
                    str(tok.get("access_token", "")), str(tok.get("refresh_token", "")),
                )
                self._health.auth_state = AUTH_CONNECTED
                self._health.user_code = ""
                logger.info("[GitHub] Authorisation complete.")
                # Connecting implies intent to use it: turn the integration on and
                # persist that, so polling also resumes after a service restart
                # (start() gates on enabled ∧ token).
                self._enable_in_config()
                await self._connect()
                return
            self._health.auth_state = AUTH_DISCONNECTED
            self._health.record_error("device code expired")
        except asyncio.CancelledError:  # pragma: no cover - shutdown/logout
            pass

    def _enable_in_config(self) -> None:
        """Persist ``github.enabled = True`` so polling survives a restart."""
        try:
            from ...config import ConfigManager
            if not getattr(self._gh, "enabled", False):
                ConfigManager.update({"github": {"enabled": True}})
                self._gh = ConfigManager.get().github
                self._health.enabled = True
                logger.info("[GitHub] Integration enabled after sign-in.")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[GitHub] could not persist enabled flag: %s", exc)

    async def logout(self) -> None:
        # Delete our hooks while the token is still valid; keep the user's
        # webhook_enabled preference so a later re-login restores them.
        try:
            await self._delete_remote_hooks()
        except Exception:  # pragma: no cover - best-effort
            pass
        secrets_store.clear_github_token()
        if self._auth_task is not None:
            self._auth_task.cancel()
            self._auth_task = None
        await self._teardown_poller()
        self.account = ""
        self._health.account = ""
        self._health.auth_state = AUTH_DISCONNECTED
        self._health.user_code = ""

    # --- read APIs for the UI -------------------------------------------
    def status(self) -> Dict[str, Any]:
        return self._health.snapshot()

    async def list_orgs(self) -> List[Dict[str, Any]]:
        if self._api is None:
            return self._cached("orgs")
        try:
            orgs = await self._api.get_user_orgs()
            slim = [{"login": o.get("login", ""), "avatar_url": o.get("avatar_url", "")} for o in orgs]
            self._ensure_store().set_cache("orgs", slim)
            return slim
        except Exception as exc:
            self._health.record_error(str(exc))
            return self._cached("orgs")

    async def list_repos(self) -> List[Dict[str, Any]]:
        if self._api is None:
            return self._cached("repos")
        try:
            repos = await self._api.get_user_repos()
            slim = [
                {
                    "full_name": r.get("full_name", ""),
                    "private": bool(r.get("private")),
                    "owner": (r.get("owner") or {}).get("login", ""),
                }
                for r in repos
            ]
            self._ensure_store().set_cache("repos", slim)
            return slim
        except Exception as exc:
            self._health.record_error(str(exc))
            return self._cached("repos")

    async def list_workflows(self, repo: str) -> List[Dict[str, Any]]:
        repo = str(repo or "").strip()
        cache_key = f"workflows:{repo.lower()}"
        if not repo or self._api is None:
            return self._cached(cache_key)
        try:
            workflows = await self._api.get_repo_workflows(repo)
            # Trim names to match normalize.* (which strips workflow names on
            # incoming events); otherwise a padded picker value like "  Build  "
            # would never match the "Build" carried by events. Drop entries that
            # are empty/whitespace-only after trimming.
            slim = []
            for w in workflows:
                name = str(w.get("name", "") or "").strip()
                if not name:
                    continue
                slim.append({
                    "name": name,
                    "path": w.get("path", ""),
                    "state": w.get("state", ""),
                })
            self._ensure_store().set_cache(cache_key, slim)
            return slim
        except Exception as exc:
            self._health.record_error(str(exc))
            return self._cached(cache_key)

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            return self._ensure_store().recent(limit)
        except Exception:
            return []

    def test_flash(self, color: Optional[list] = None) -> None:
        """Flash now so the user can preview a colour without a real event."""
        gh = self._gh
        rgb = color or list(getattr(gh, "default_color", [88, 166, 255]))
        try:
            self._controller.flash(rgb, self._default_pattern(), label="GitHub test")
        except Exception as exc:
            logger.debug("[GitHub] test flash failed: %s", exc)

    # --- helpers ---------------------------------------------------------
    def _cached(self, key: str) -> List[Dict[str, Any]]:
        if self._store is None:
            return []
        return self._store.get_cache(key) or []

    def _schedule(self, coro) -> None:
        """Fire-and-forget a coroutine on the loop thread."""
        try:
            asyncio.ensure_future(coro)
        except RuntimeError:  # pragma: no cover - no running loop
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(lambda: asyncio.ensure_future(coro))
