"""
LedDriver interface (A0)
========================
The uniform contract every LED protocol implements. It is the exact surface the
pipeline run loop and the API already use against ``MagicHomeController``, so
swapping in the factory changes nothing for existing devices.

Consumers (for reference):
  * ``pipeline.py`` run loop: ``connect``, ``turn_on``/``turn_off``,
    ``ensure_on``, ``set_rgb``, ``set_pixels``, ``disconnect`` and the
    ``is_connected`` / ``is_addressable`` properties plus the ``led_count``
    attribute.
  * ``api_server.py`` device flash: ``connect``, ``turn_on``, ``set_rgb``,
    ``disconnect``.

Implementations also expose ``led_count: int`` (a plain attribute or property —
used to size gradients) and may expose ``kind``/``ip``/``last_color``; these are
not enforced abstractly so a driver can keep ``led_count`` as a simple instance
attribute.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LedDriver(ABC):
    """Abstract base for a single addressable-or-single-colour LED device."""

    # --- connection lifecycle ---------------------------------------------
    @abstractmethod
    def connect(self) -> bool:
        """Open the device connection. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and release resources."""

    # --- power ------------------------------------------------------------
    @abstractmethod
    def turn_on(self) -> bool:
        """Power the device on. Returns True on success."""

    @abstractmethod
    def turn_off(self) -> bool:
        """Power the device off. Returns True on success."""

    @abstractmethod
    def ensure_on(self) -> bool:
        """Power on only if currently off/unknown (avoids redundant commands)."""

    def query_power(self) -> Optional[bool]:
        """Best-effort current power state, or ``None`` if unknown/unreachable.

        Optional — drivers that can't query power may rely on the tracked
        :attr:`power_on`. Default returns ``None``.
        """
        return None

    # --- output -----------------------------------------------------------
    @abstractmethod
    def set_rgb(self, r: int, g: int, b: int) -> bool:
        """Set a single colour for the whole device. Returns True if sent."""

    @abstractmethod
    def set_pixels(self, pixels: "list[tuple[int, int, int]]") -> bool:
        """Set per-LED colours (addressable devices). Returns True if sent."""

    # --- state (properties) ----------------------------------------------
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True while the device connection is believed healthy."""

    @property
    @abstractmethod
    def is_addressable(self) -> bool:
        """True when the device supports per-LED (``set_pixels``) output."""

    @property
    def power_on(self) -> Optional[bool]:
        """Last-known power state (True/False, or None if never determined)."""
        return None
