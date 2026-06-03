"""
LED Output Module
=================
Manages communication with a MagicHome LED controller over the proprietary
TCP protocol (port 5577), implementing:

* Thread-safe socket access via a re-entrant lock.
* Duplicate-suppression: skips transmission when colour is unchanged.
* Rate limiting: respects a configurable minimum interval between sends.
* Automatic reconnect with exponential back-off.
* Graceful shutdown.

Protocol
--------
MagicHome uses a simple binary protocol:

    Turn ON  : 71 23 0f
    Turn OFF : 71 24 0f
    Set RGB  : 31 <R> <G> <B> 00 f0 0f  (checksum = last byte of byte-sum)

Checksum is the low byte of the sum of all preceding bytes.

References
----------
* flux_led open-source implementation (Apache 2.0):
  https://github.com/Danielhiversen/flux_led
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# MagicHome TCP port
_MAGIC_PORT = 5577

# Protocol constants
_CMD_ON = bytes([0x71, 0x23, 0x0F])
_CMD_OFF = bytes([0x71, 0x24, 0x0F])


def _build_rgb_command(r: int, g: int, b: int) -> bytes:
    """
    Build the MagicHome Set-RGB command with checksum.

    Parameters
    ----------
    r, g, b:
        Red, green, blue values (0–255).

    Returns
    -------
    bytes
        7-byte command payload ready to send over TCP.
    """
    payload = bytes([0x31, r & 0xFF, g & 0xFF, b & 0xFF, 0x00, 0xF0, 0x0F])
    checksum = sum(payload) & 0xFF
    return payload + bytes([checksum])


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class MagicHomeController:
    """
    Thread-safe MagicHome LED controller.

    Parameters
    ----------
    ip:
        IP address of the controller.
    port:
        TCP port (default 5577).
    connect_timeout:
        Socket connect timeout in seconds.
    send_timeout:
        Socket send timeout in seconds.
    reconnect_interval:
        Minimum seconds to wait between reconnect attempts.
    min_update_interval:
        Minimum seconds between colour sends (rate limiting).
    """

    def __init__(
        self,
        ip: str,
        port: int = _MAGIC_PORT,
        connect_timeout: float = 2.0,
        send_timeout: float = 1.0,
        reconnect_interval: float = 5.0,
        min_update_interval: float = 0.033,  # ~30 fps max
        reconnect_backoff_max: float = 30.0,
        kind: str = "single",          # "single" | "addressable" | "rgbw"
        led_count: int = 30,           # addressable strip length
    ) -> None:
        self._ip = ip
        self._port = port
        self._connect_timeout = connect_timeout
        self._send_timeout = send_timeout
        self._reconnect_interval = reconnect_interval
        self._reconnect_backoff_max = reconnect_backoff_max
        self._min_update_interval = min_update_interval
        self.kind = kind
        self.led_count = led_count

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._last_color: Optional[tuple[int, int, int]] = None
        self._last_send_time: float = 0.0
        self._last_reconnect_attempt: float = 0.0
        self._reconnect_failures: int = 0
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Establish a TCP connection to the controller.

        Returns *True* on success, *False* on failure.
        """
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        """Internal connect — caller must hold ``_lock``."""
        self._disconnect_locked()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self._connect_timeout)
            sock.connect((self._ip, self._port))
            sock.settimeout(self._send_timeout)
            # Disable Nagle algorithm for lower latency
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            self._connected = True
            logger.info(
                "[LED] Connected to MagicHome controller at %s:%d.",
                self._ip, self._port,
            )
            return True
        except (OSError, socket.timeout) as exc:
            logger.warning("[LED] Connection failed: %s", exc)
            self._sock = None
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close the socket gracefully."""
        with self._lock:
            self._disconnect_locked()

    def _disconnect_locked(self) -> None:
        """Internal disconnect — caller must hold ``_lock``."""
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._connected = False

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def turn_on(self) -> bool:
        """Send the turn-on command.  Returns *True* on success."""
        return self._send_raw(_CMD_ON)

    def turn_off(self) -> bool:
        """Send the turn-off command.  Returns *True* on success."""
        return self._send_raw(_CMD_OFF)

    def set_rgb(self, r: int, g: int, b: int) -> bool:
        """
        Set the LED colour.

        Skips the transmission when:

        * The colour is identical to the last transmitted colour.
        * The minimum update interval has not elapsed.

        Parameters
        ----------
        r, g, b:
            Red, green, blue values (0–255).

        Returns
        -------
        bool
            *True* if the command was transmitted successfully.
        """
        color = (r & 0xFF, g & 0xFF, b & 0xFF)

        # Duplicate suppression
        if color == self._last_color:
            return True

        # Rate limiting
        now = time.monotonic()
        if now - self._last_send_time < self._min_update_interval:
            return True

        cmd = _build_rgb_command(*color)
        success = self._send_raw(cmd)
        if success:
            self._last_color = color
            self._last_send_time = now
        return success

    def set_pixels(self, pixels: list[tuple[int, int, int]]) -> bool:
        """
        Set addressable (per-LED) pixels on an SPI MagicHome controller.

        Protocol note
        -------------
        Addressable MagicHome / flux_led controllers accept a custom-frame
        command. The framing below follows the common ``0x41`` per-pixel form
        (header + RGB triplets + trailer + checksum). **This path is exercised
        only for devices classified ``addressable`` and has NOT been validated
        against physical addressable hardware — verify framing before relying on
        it in production.** Single-RGB devices never reach this method.

        Parameters
        ----------
        pixels:
            Ordered list of (R, G, B) tuples, one per LED.
        """
        # Rate limiting (shared with set_rgb)
        now = time.monotonic()
        if now - self._last_send_time < self._min_update_interval:
            return True

        payload = bytearray([0x41])              # custom per-pixel frame
        for r, g, b in pixels:
            payload.extend((r & 0xFF, g & 0xFF, b & 0xFF))
        payload.append(0x0F)                     # trailer
        payload.append(sum(payload) & 0xFF)      # checksum

        success = self._send_raw(bytes(payload))
        if success:
            self._last_send_time = now
        return success

    # ------------------------------------------------------------------
    # Internal send with reconnect logic
    # ------------------------------------------------------------------

    def _send_raw(self, data: bytes) -> bool:
        """
        Send *data* over the socket.

        If the socket is not connected or the send fails, an automatic
        reconnect is attempted (subject to *reconnect_interval* back-off).
        """
        with self._lock:
            if not self._connected:
                if not self._maybe_reconnect():
                    return False

            try:
                self._sock.sendall(data)  # type: ignore[union-attr]
                return True
            except (OSError, socket.timeout) as exc:
                logger.warning("[LED] Send failed: %s — reconnecting.", exc)
                self._connected = False
                if self._maybe_reconnect():
                    try:
                        self._sock.sendall(data)  # type: ignore[union-attr]
                        return True
                    except OSError as exc2:
                        logger.error("[LED] Re-send after reconnect failed: %s", exc2)
                return False

    def _current_backoff(self) -> float:
        """Capped exponential back-off based on consecutive failures."""
        backoff = self._reconnect_interval * (2 ** self._reconnect_failures)
        return min(backoff, self._reconnect_backoff_max)

    def _maybe_reconnect(self) -> bool:
        """
        Attempt reconnect if the back-off interval has passed.

        Uses capped exponential back-off (FR-DEV-08): the wait grows
        ``reconnect_interval × 2ⁿ`` after each consecutive failure, up to
        ``reconnect_backoff_max`` seconds, and resets on success.

        Returns *True* if now connected.
        """
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._current_backoff():
            return False
        self._last_reconnect_attempt = now
        logger.info("[LED] Attempting reconnect to %s:%d …", self._ip, self._port)
        success = self._connect_locked()
        if success:
            self._reconnect_failures = 0
            logger.info("[LED] Reconnect successful.")
        else:
            self._reconnect_failures += 1
            logger.warning(
                "[LED] Reconnect failed; will retry in %.0f s.",
                self._current_backoff(),
            )
        return success

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ip(self) -> str:
        return self._ip

    @ip.setter
    def ip(self, value: str) -> None:
        """Update IP and force a reconnect on next send."""
        with self._lock:
            if value != self._ip:
                logger.info("[LED] IP changed: %s → %s", self._ip, value)
                self._ip = value
                self._disconnect_locked()

    @property
    def is_addressable(self) -> bool:
        return self.kind == "addressable"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_color(self) -> Optional[tuple[int, int, int]]:
        return self._last_color

    def __repr__(self) -> str:
        return (
            f"MagicHomeController(ip={self._ip!r}, "
            f"connected={self._connected}, "
            f"last_color={self._last_color})"
        )
