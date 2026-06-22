"""
Secret storage (OS keyring)
===========================
Keeps secrets — currently the MQTT broker password — out of
``configuration.yaml`` by storing them in the OS credential store via the
optional ``keyring`` package (Windows Credential Manager / macOS Keychain /
Linux Secret Service).

``keyring`` is an **optional** dependency: if it isn't installed, or the
platform has no usable backend (common on headless Linux), we fall back to an
in-process value so the bridge still works for the running session — it just
isn't persisted across restarts, and a warning is logged. The password is never
written to the YAML config regardless (see the scrub-on-save hook in
``api_server``).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SERVICE = "ambilight"
_MQTT_KEY = "mqtt_password"

# Session fallback when keyring is unavailable (module-level, process-lifetime).
_fallback: dict[str, str] = {}


def _keyring():
    """Return the ``keyring`` module if usable, else ``None`` (cached check)."""
    try:
        import keyring  # optional dependency
        return keyring
    except Exception:  # pragma: no cover - depends on environment
        return None


def set_mqtt_password(password: str) -> None:
    """Persist the MQTT broker password to the OS keyring (or session fallback)."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(_SERVICE, _MQTT_KEY, password or "")
            _fallback.pop(_MQTT_KEY, None)
            return
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning("[Secrets] keyring set failed (%s); using session fallback.", exc)
    _fallback[_MQTT_KEY] = password or ""


def get_mqtt_password() -> str:
    """Return the stored MQTT broker password, or '' if none."""
    kr = _keyring()
    if kr is not None:
        try:
            pw = kr.get_password(_SERVICE, _MQTT_KEY)
            if pw is not None:
                return pw
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning("[Secrets] keyring get failed (%s); using session fallback.", exc)
    return _fallback.get(_MQTT_KEY, "")


def clear_mqtt_password() -> None:
    """Remove the stored MQTT broker password from keyring + session fallback."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(_SERVICE, _MQTT_KEY)
        except Exception:  # pragma: no cover - may not exist / backend-specific
            pass
    _fallback.pop(_MQTT_KEY, None)
