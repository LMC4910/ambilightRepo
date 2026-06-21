"""
Device drivers
==============
Protocol-specific LED controllers behind a uniform :class:`LedDriver` interface
(A0). The pipeline talks only to ``LedDriver``; :func:`create_driver` picks the
concrete driver from a device spec's ``protocol`` field, so new protocols
(WLED, …) slot in without touching the capture/colour/effects code.
"""

from __future__ import annotations

from .base import LedDriver
from .factory import create_driver

__all__ = ["LedDriver", "create_driver"]
