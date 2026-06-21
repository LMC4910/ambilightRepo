"""
LED Output Module (compatibility shim)
=======================================
The MagicHome controller moved to :mod:`ambilight.devices.magichome` as part of
the multi-protocol driver abstraction (A0). This module re-exports it so the
existing ``from ambilight.led_output import MagicHomeController`` imports (and
the test suite) keep working unchanged. New code should depend on
:class:`ambilight.devices.LedDriver` and :func:`ambilight.devices.create_driver`.
"""

from __future__ import annotations

from .devices.magichome import (
    MagicHomeController,
    _build_rgb_command,
    _CMD_OFF,
    _CMD_ON,
    _CMD_QUERY_STATE,
    _MAGIC_PORT,
)

__all__ = [
    "MagicHomeController",
    "_build_rgb_command",
    "_MAGIC_PORT",
    "_CMD_ON",
    "_CMD_OFF",
    "_CMD_QUERY_STATE",
]
