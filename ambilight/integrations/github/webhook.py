"""
GitHub integration — webhook receiver helpers (optional / advanced)
===================================================================
Polling is the default delivery path (it works behind NAT). For power users who
*can* expose an endpoint (a tunnel like cloudflared/ngrok, or a future cloud
relay), GitHub can also push events as webhooks. Both paths feed the same
:func:`normalize.normalize_webhook`, so enabling webhooks changes nothing
downstream.

This module holds the pure, testable bits — HMAC-SHA256 signature verification
and header parsing — used by the receiver route wired into ``api_server``. The
shared secret lives in the OS keyring (never in the YAML config), exactly like
the MQTT password.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional, Tuple

# Keyring key for the webhook shared secret (used via secrets_store.set/get_secret).
WEBHOOK_SECRET_KEY = "github_webhook_secret"


def verify_signature(secret: str, body: bytes, signature_header: Optional[str]) -> bool:
    """Constant-time check of GitHub's ``X-Hub-Signature-256`` header.

    GitHub signs the raw request body with HMAC-SHA256 keyed by the webhook
    secret and sends ``sha256=<hexdigest>``. Returns ``False`` for any missing
    secret / header or mismatch — fail closed.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parse_headers(headers) -> Tuple[str, str]:
    """Extract ``(event_name, delivery_id)`` from request headers (case-insensitive)."""
    def _get(name: str) -> str:
        try:
            return headers.get(name, "") or ""
        except Exception:
            return ""

    event = _get("X-GitHub-Event") or _get("x-github-event")
    delivery = _get("X-GitHub-Delivery") or _get("x-github-delivery")
    return str(event), str(delivery)
