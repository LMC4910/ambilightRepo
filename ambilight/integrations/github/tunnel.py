"""
GitHub integration — public-reachability tunnel (cloudflared)
=============================================================
The desktop app's API server binds to ``127.0.0.1`` (loopback), so GitHub's
servers cannot POST webhook deliveries to it directly. To make webhooks work
without standing up a cloud relay, we run **cloudflared** as a child process: it
opens an outbound connection to Cloudflare's edge and gives us a public HTTPS
URL that forwards back to our loopback receiver.

Two modes:

* **Quick tunnel** (default, zero-config): ``cloudflared tunnel --url <local>``
  prints a one-off ``https://<random>.trycloudflare.com`` URL. No account needed,
  but the hostname changes every launch (so the service re-points its GitHub
  hooks each start) and Cloudflare offers no SLA on it.
* **Named tunnel** (opt-in, stable): ``cloudflared tunnel run --token <token>``
  with a token from the keyring, fronted by a hostname the user owns. The URL is
  stable, so hooks don't churn.

The pure URL-parsing logic (:func:`parse_public_url`) is split out so it can be
unit-tested without spawning a process.

Security note: a quick tunnel exposes the *whole* loopback server publicly. That
is acceptable because the webhook route is HMAC-verified and every other route
requires the per-session Bearer token, but a named-tunnel deployment should scope
a cloudflared ingress rule to just ``/api/github/webhook``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from typing import Optional

from ...paths import resource_path

logger = logging.getLogger(__name__)

# cloudflared advertises the quick-tunnel hostname on a line like:
#   "...  |  https://calm-frog-1234.trycloudflare.com  |  ..."
_TRYCLOUDFLARE_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def parse_public_url(line: str) -> Optional[str]:
    """Return the ``*.trycloudflare.com`` URL in *line*, or ``None``.

    Pure helper (no I/O) so the parsing is unit-testable.
    """
    if not line:
        return None
    m = _TRYCLOUDFLARE_RE.search(line)
    return m.group(0) if m else None


def _binary_name() -> str:
    return "cloudflared.exe" if sys.platform.startswith("win") else "cloudflared"


def locate_cloudflared() -> Optional[str]:
    """Find the cloudflared binary: bundled ``bin/`` first, then ``PATH``.

    Returns the absolute path, or ``None`` when it can't be found (the caller
    then stays on polling and surfaces a clear error).
    """
    name = _binary_name()
    # 1. Bundled with the app (build.py ships it under bin/).
    try:
        bundled = resource_path(os.path.join("bin", name))
        if os.path.isfile(bundled):
            return bundled
    except Exception:
        pass
    # 2. On PATH (a user who installed cloudflared themselves).
    found = shutil.which(name) or shutil.which("cloudflared")
    return found


class TunnelError(RuntimeError):
    """Raised when the tunnel cannot be established."""


class CloudflaredTunnel:
    """Manage a cloudflared child process and expose its public URL.

    Lifecycle: :meth:`start` (idempotent) spawns the process and resolves the
    public URL; a background task restarts the process if it dies while we still
    want it up; :meth:`stop` tears it down.
    """

    def __init__(self, local_url: str = "http://127.0.0.1:7826", *,
                 named: bool = False, hostname: str = "",
                 token: str = "", binary: Optional[str] = None) -> None:
        self._local_url = local_url
        self._named = bool(named)
        self._hostname = (hostname or "").strip()
        self._token = (token or "").strip()
        self._binary = binary  # override (tests); else resolved at start()
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._monitor: Optional[asyncio.Task] = None
        self._url_ready = asyncio.Event()
        self._want_running = False
        self.public_url: str = ""
        self.error: str = ""

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def _build_argv(self, binary: str) -> list[str]:
        if self._named and self._token:
            # Stable named tunnel fronted by the user's hostname.
            return [binary, "tunnel", "--no-autoupdate", "run", "--token", self._token]
        # Zero-config quick tunnel.
        return [binary, "tunnel", "--no-autoupdate", "--url", self._local_url]

    async def start(self, timeout: float = 30.0) -> Optional[str]:
        """Spawn cloudflared and return the public URL (or ``None`` on failure).

        Idempotent: returns the existing URL if already running.
        """
        if self.running and self.public_url:
            return self.public_url
        binary = self._binary or locate_cloudflared()
        if not binary:
            self.error = (
                "cloudflared not found. Install it or bundle it under bin/ to use "
                "webhook delivery; staying on polling."
            )
            logger.warning("[GitHub] %s", self.error)
            return None

        self._want_running = True
        self._url_ready.clear()
        try:
            await self._spawn(binary)
        except Exception as exc:  # pragma: no cover - spawn is environment-specific
            self.error = f"failed to start cloudflared: {exc}"
            logger.warning("[GitHub] %s", self.error)
            return None

        # A named tunnel has a known, stable URL — no need to scrape stdout.
        if self._named and self._hostname:
            self.public_url = self._hostname if self._hostname.startswith("http") else f"https://{self._hostname}"
            self._url_ready.set()

        try:
            await asyncio.wait_for(self._url_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.error = "cloudflared did not report a public URL in time"
            logger.warning("[GitHub] %s", self.error)
            await self.stop()
            return None
        self.error = ""
        logger.info("[GitHub] Tunnel up: %s -> %s", self.public_url, self._local_url)
        return self.public_url

    async def _spawn(self, binary: str) -> None:
        argv = self._build_argv(binary)
        # Merge stderr into stdout: cloudflared logs the quick-tunnel URL to stderr.
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._monitor = asyncio.create_task(
            self._read_and_watch(self._proc), name="github-cloudflared",
        )

    async def _read_and_watch(self, proc: asyncio.subprocess.Process) -> None:
        """Scan output for the public URL, then watch for unexpected exit."""
        try:
            assert proc.stdout is not None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip()
                if not self._url_ready.is_set():
                    url = parse_public_url(line)
                    if url:
                        self.public_url = url
                        self._url_ready.set()
            # Stream closed → process is exiting. Reap it.
            await proc.wait()
        except asyncio.CancelledError:  # pragma: no cover - shutdown
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[GitHub] tunnel reader error: %s", exc)

        # If we still want it running, the tunnel died unexpectedly — restart it
        # (the public URL likely changed, so the service must re-register hooks;
        # it watches health/status and reconciles).
        if self._want_running:
            self.public_url = ""
            self._url_ready.clear()
            self.error = "tunnel exited; restarting"
            logger.warning("[GitHub] cloudflared exited (code=%s); restarting in 5s.",
                           getattr(proc, "returncode", "?"))
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:  # pragma: no cover
                return
            if self._want_running:
                binary = self._binary or locate_cloudflared()
                if binary:
                    try:
                        await self._spawn(binary)
                    except Exception as exc:  # pragma: no cover
                        self.error = f"tunnel restart failed: {exc}"

    async def stop(self) -> None:
        """Terminate cloudflared and stop restarting it."""
        self._want_running = False
        self._url_ready.clear()
        self.public_url = ""
        if self._monitor is not None:
            self._monitor.cancel()
            try:
                await self._monitor
            except (asyncio.CancelledError, Exception):
                pass
            self._monitor = None
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:  # pragma: no cover - already gone
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, Exception):
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
