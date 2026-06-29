"""
GitHub integration — health / status snapshot
==============================================
A small mutable status object the poller and auth flow update, and the
``/api/github/status`` endpoint reads. Kept deliberately plain (no locking) —
every writer runs on the asyncio loop thread.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# auth_state values
AUTH_DISCONNECTED = "disconnected"
AUTH_PENDING = "pending"      # device flow started, awaiting user
AUTH_CONNECTED = "connected"


@dataclass
class GithubHealth:
    enabled: bool = False
    httpx_available: bool = True
    auth_state: str = AUTH_DISCONNECTED
    account: str = ""
    # Device-flow prompt (only meaningful while auth_state == "pending").
    user_code: str = ""
    verification_uri: str = ""
    auth_expires_at: float = 0.0
    # Polling / rate-limit telemetry.
    last_poll_ts: float = 0.0
    last_event_ts: float = 0.0
    poll_interval_s: float = 0.0
    rate_remaining: int = -1
    rate_limit: int = -1
    watched_repos: int = 0
    # Webhook / tunnel telemetry (event-driven delivery path).
    webhook_active: bool = False           # tunnel up AND ≥1 hook registered
    tunnel_public_url: str = ""            # current public URL (empty when off)
    tunnel_error: str = ""                 # last tunnel failure (binary missing, etc.)
    # Per-repo/org hook state: full_name -> "registered" | "polling-fallback" |
    # "needs-admin" | "error". Drives the UI badges.
    hook_status: Dict[str, str] = field(default_factory=dict)
    last_delivery_ts: float = 0.0          # last received webhook delivery
    # Errors.
    last_error: str = ""
    error_count: int = 0

    def snapshot(self) -> Dict[str, Any]:
        d = {
            "enabled": self.enabled,
            "httpx_available": self.httpx_available,
            "auth_state": self.auth_state,
            "connected": self.auth_state == AUTH_CONNECTED,
            "account": self.account,
            "last_poll_ts": self.last_poll_ts,
            "last_event_ts": self.last_event_ts,
            "poll_interval_s": self.poll_interval_s,
            "rate_remaining": self.rate_remaining,
            "rate_limit": self.rate_limit,
            "watched_repos": self.watched_repos,
            "webhook_active": self.webhook_active,
            "tunnel_public_url": self.tunnel_public_url,
            "tunnel_error": self.tunnel_error,
            "hook_status": dict(self.hook_status),
            "last_delivery_ts": self.last_delivery_ts,
            "last_error": self.last_error,
            "error_count": self.error_count,
        }
        if self.auth_state == AUTH_PENDING:
            d["user_code"] = self.user_code
            d["verification_uri"] = self.verification_uri
            d["auth_expires_in"] = max(0, int(self.auth_expires_at - time.time()))
        return d

    def record_error(self, message: str) -> None:
        self.last_error = str(message)[:300]
        self.error_count += 1
