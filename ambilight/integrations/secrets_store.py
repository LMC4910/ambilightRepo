"""
Secret storage (OS keyring)
===========================
Keeps secrets — the MQTT broker password and integration tokens (e.g. the GitHub
OAuth access/refresh tokens) — out of ``configuration.yaml`` by storing them in
the OS credential store via the optional ``keyring`` package (Windows Credential
Manager / macOS Keychain / Linux Secret Service).

``keyring`` is an **optional** dependency: if it isn't installed, or the
platform has no usable backend (common on headless Linux), we fall back to an
in-process value so the integration still works for the running session — it just
isn't persisted across restarts, and a warning is logged. Secrets are never
written to the YAML config regardless (see the scrub-on-save hook in
``api_server`` / ``config``).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SERVICE = "ambilight"
_MQTT_KEY = "mqtt_password"
_GITHUB_TOKEN_KEY = "github_token"
_GITHUB_REFRESH_KEY = "github_refresh_token"

# Session fallback when keyring is unavailable (module-level, process-lifetime).
_fallback: dict[str, str] = {}


def _keyring():
    """Return the ``keyring`` module if usable, else ``None`` (cached check)."""
    try:
        import keyring  # optional dependency
        return keyring
    except Exception:  # pragma: no cover - depends on environment
        return None


# --- generic secret API (reusable by any integration) ----------------------

def set_secret(key: str, value: str) -> None:
    """Persist an arbitrary secret to the OS keyring (or session fallback)."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(_SERVICE, key, value or "")
            _fallback.pop(key, None)
            return
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning("[Secrets] keyring set failed (%s); using session fallback.", exc)
    _fallback[key] = value or ""


def get_secret(key: str) -> str:
    """Return a stored secret, or '' if none."""
    kr = _keyring()
    if kr is not None:
        try:
            v = kr.get_password(_SERVICE, key)
            if v is not None:
                return v
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning("[Secrets] keyring get failed (%s); using session fallback.", exc)
    return _fallback.get(key, "")


def clear_secret(key: str) -> None:
    """Remove a stored secret from keyring + session fallback."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(_SERVICE, key)
        except Exception as exc:  # pragma: no cover - may not exist / backend-specific
            # Surface the failure: the OS entry may persist and later reappear, so
            # silently swallowing it would hide stale-secret retention.
            logger.warning("[Secrets] keyring delete failed (%s); entry may persist.", exc)
    _fallback.pop(key, None)


# --- MQTT broker password (back-compat wrappers) ---------------------------

def set_mqtt_password(password: str) -> None:
    """Persist the MQTT broker password to the OS keyring (or session fallback)."""
    set_secret(_MQTT_KEY, password)


def get_mqtt_password() -> str:
    """Return the stored MQTT broker password, or '' if none."""
    return get_secret(_MQTT_KEY)


def clear_mqtt_password() -> None:
    """Remove the stored MQTT broker password from keyring + session fallback."""
    clear_secret(_MQTT_KEY)


# --- GitHub OAuth tokens ---------------------------------------------------

def set_github_token(token: str, refresh_token: str = "") -> None:
    """Persist the GitHub access token (+ optional refresh token)."""
    set_secret(_GITHUB_TOKEN_KEY, token)
    if refresh_token:
        set_secret(_GITHUB_REFRESH_KEY, refresh_token)


def get_github_token() -> str:
    """Return the stored GitHub access token, or '' if none."""
    return get_secret(_GITHUB_TOKEN_KEY)


def get_github_refresh_token() -> str:
    """Return the stored GitHub refresh token, or '' if none."""
    return get_secret(_GITHUB_REFRESH_KEY)


def clear_github_token() -> None:
    """Remove the GitHub access + refresh tokens."""
    clear_secret(_GITHUB_TOKEN_KEY)
    clear_secret(_GITHUB_REFRESH_KEY)
