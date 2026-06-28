"""
GitHub integration — OAuth Device Flow
======================================
Implements GitHub's `device authorization grant
<https://docs.github.com/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow>`_,
the right fit for a desktop app: the app ships only a public ``client_id`` (no
secret), the user authorises by typing a short ``user_code`` at
``https://github.com/login/device``, and we poll for the resulting token.

Two calls:

* :func:`request_device_code` — start the flow, returns the user-facing code +
  verification URL and the ``device_code`` we poll with.
* :func:`poll_for_token` — exchange the ``device_code`` for an access token;
  raises :class:`DeviceFlowPending` / :class:`DeviceFlowSlowDown` while the user
  hasn't finished, and :class:`DeviceFlowError` on a terminal failure.

The caller (the integration service) owns the polling loop so it can cancel,
honour ``interval``/``slow_down`` and persist the token to the keyring.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .api import WEB_BASE

logger = logging.getLogger(__name__)

_DEVICE_CODE_URL = f"{WEB_BASE}/login/device/code"
_TOKEN_URL = f"{WEB_BASE}/login/oauth/access_token"
_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# Classic OAuth scopes requested by default. ``repo`` is broad but is what reads
# private-repo workflow runs / events; ``notifications`` powers the inbox feed;
# ``read:org`` lists the user's orgs. The set is configurable in GithubConfig.
DEFAULT_SCOPES = ("notifications", "read:org", "repo")


class DeviceFlowPending(Exception):
    """User hasn't authorised yet — keep polling at the current interval."""


class DeviceFlowSlowDown(Exception):
    """GitHub asked us to back off; the new interval is on ``.interval``."""

    def __init__(self, interval: int) -> None:
        super().__init__("slow_down")
        self.interval = interval


class DeviceFlowError(Exception):
    """Terminal failure (expired code, access denied, bad client, ...)."""


async def request_device_code(client_id: str, scopes=DEFAULT_SCOPES,
                              timeout: float = 15.0) -> Dict[str, Any]:
    """Start the device flow. Returns GitHub's device-code response dict:
    ``{device_code, user_code, verification_uri, expires_in, interval}``."""
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _DEVICE_CODE_URL,
            headers={"Accept": "application/json", "User-Agent": "Ambilight-Desktop"},
            data={"client_id": client_id, "scope": " ".join(scopes)},
        )
    if resp.status_code != 200:
        raise DeviceFlowError(f"device code request failed: HTTP {resp.status_code}")
    data = resp.json()
    if "device_code" not in data:
        raise DeviceFlowError(str(data.get("error_description") or data.get("error") or data))
    return data


async def poll_for_token(client_id: str, device_code: str,
                         timeout: float = 15.0) -> Dict[str, Any]:
    """Exchange *device_code* for a token.

    Returns the token dict ``{access_token, token_type, scope, ...}`` on success.
    Raises :class:`DeviceFlowPending` / :class:`DeviceFlowSlowDown` /
    :class:`DeviceFlowError` otherwise.
    """
    import httpx

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _TOKEN_URL,
            headers={"Accept": "application/json", "User-Agent": "Ambilight-Desktop"},
            data={"client_id": client_id, "device_code": device_code, "grant_type": _GRANT},
        )
    data = resp.json() if resp.content else {}
    if data.get("access_token"):
        return data

    error = str(data.get("error", "") or "")
    if error == "authorization_pending":
        raise DeviceFlowPending()
    if error == "slow_down":
        try:
            interval = int(data.get("interval", 5))
        except (TypeError, ValueError):
            interval = 5
        raise DeviceFlowSlowDown(interval)
    # expired_token, access_denied, incorrect_client_credentials, ...
    raise DeviceFlowError(str(data.get("error_description") or error or "unknown error"))
