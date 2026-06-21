"""
WLED LED driver (A1)
====================
Drives a `WLED <https://kno.wled.ge>`_ controller — the most popular DIY
addressable controller — behind the :class:`~ambilight.devices.base.LedDriver`
interface.

Two channels, matching how Hyperion/Prismatik drive WLED:

* **Realtime per-pixel — UDP port 21324.** The hot path. WLED's realtime UDP
  protocols carry raw pixels with almost no latency:
    - **DRGB** (protocol ``2``): ``[2, timeout] + RGB*n`` for up to 490 LEDs.
    - **DNRGB** (protocol ``4``): ``[4, timeout, startHi, startLo] + RGB*n`` for
      longer strips, sent as chunks with a start index.
  The ``timeout`` byte tells WLED how many seconds to stay in realtime before
  reverting to its normal effect if packets stop.
* **Power / brightness — JSON API over HTTP** (stdlib ``urllib``; no new dep):
  ``POST /json/state`` for on/off, ``GET /json/info`` for the LED count.

WLED is always addressable, so the pipeline's gradient → :meth:`set_pixels`
path drives it per-pixel.
"""

from __future__ import annotations

import json
import logging
import socket
import time
import urllib.request
from typing import Optional

from .base import LedDriver

logger = logging.getLogger(__name__)

# Fixed WLED realtime UDP port and per-packet LED limits (kept under a 1472-byte
# UDP payload): DRGB has a 2-byte header (→ 490 LEDs), DNRGB a 4-byte header with
# a 16-bit start index (→ 489 LEDs/chunk).
_REALTIME_PORT = 21324
_DRGB_MAX = 490
_DNRGB_CHUNK = 489
# Seconds WLED stays in realtime after our last packet before reverting.
_REALTIME_TIMEOUT = 2


def build_realtime_packets(
    pixels: "list[tuple[int, int, int]]",
    timeout: int = _REALTIME_TIMEOUT,
) -> "list[bytes]":
    """Encode *pixels* into one or more WLED realtime UDP packets.

    Returns a single DRGB packet for short strips, or chunked DNRGB packets
    (each carrying its start index) for strips longer than 490 LEDs. Empty
    input yields no packets.
    """
    n = len(pixels)
    if n == 0:
        return []

    def _rgb_bytes(seq) -> bytes:
        out = bytearray()
        for r, g, b in seq:
            out += bytes((r & 0xFF, g & 0xFF, b & 0xFF))
        return bytes(out)

    if n <= _DRGB_MAX:
        return [bytes([2, timeout]) + _rgb_bytes(pixels)]

    packets: list[bytes] = []
    for start in range(0, n, _DNRGB_CHUNK):
        chunk = pixels[start:start + _DNRGB_CHUNK]
        header = bytes([4, timeout, (start >> 8) & 0xFF, start & 0xFF])
        packets.append(header + _rgb_bytes(chunk))
    return packets


class WledDriver(LedDriver):
    """WLED controller driver (realtime UDP pixels + JSON API power)."""

    def __init__(
        self,
        ip: str,
        port: int = 80,                       # HTTP/JSON API port
        connect_timeout: float = 2.0,
        send_timeout: float = 1.0,
        reconnect_interval: float = 5.0,
        min_update_interval: float = 0.033,   # ~30 fps max
        reconnect_backoff_max: float = 30.0,
        led_count: int = 30,
        realtime_port: int = _REALTIME_PORT,
    ) -> None:
        self._ip = ip
        self._http_port = port
        self._realtime_port = realtime_port
        self._connect_timeout = connect_timeout
        self._send_timeout = send_timeout
        self._reconnect_interval = reconnect_interval
        self._reconnect_backoff_max = reconnect_backoff_max
        self._min_update_interval = min_update_interval
        self.kind = "addressable"             # WLED is always per-pixel
        self.led_count = led_count

        self._udp: Optional[socket.socket] = None
        self._last_color: Optional[tuple[int, int, int]] = None
        self._last_send_time: float = 0.0
        self._last_reconnect_attempt: float = 0.0
        self._reconnect_failures: int = 0
        self._connected: bool = False
        self._power_on: Optional[bool] = None

    # ------------------------------------------------------------------
    # HTTP JSON API helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"http://{self._ip}:{self._http_port}{path}"

    def _http_get_json(self, path: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(self._url(path))
            with urllib.request.urlopen(req, timeout=self._connect_timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("[WLED] GET %s failed: %s", path, exc)
            return None

    def _http_post_json(self, path: str, payload: dict) -> bool:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._url(path), data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._send_timeout):
                return True
        except Exception as exc:
            logger.debug("[WLED] POST %s failed: %s", path, exc)
            return False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Fetch ``/json/info`` (confirming reachability + LED count) and open
        the realtime UDP socket. Returns True on success."""
        info = self._http_get_json("/json/info")
        if info is None:
            self._connected = False
            return False
        count = info.get("leds", {}).get("count")
        if isinstance(count, int) and count > 0:
            self.led_count = count
        self._ensure_socket()
        self._connected = True
        self._reconnect_failures = 0
        logger.info("[WLED] Connected to %s:%d (%d LEDs).", self._ip, self._http_port, self.led_count)
        return True

    def _ensure_socket(self) -> None:
        if self._udp is None:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def disconnect(self) -> None:
        """Close the realtime UDP socket."""
        if self._udp is not None:
            try:
                self._udp.close()
            except OSError:
                pass
            self._udp = None
        self._connected = False

    # ------------------------------------------------------------------
    # Power (HTTP JSON state)
    # ------------------------------------------------------------------

    def turn_on(self) -> bool:
        ok = self._http_post_json("/json/state", {"on": True})
        if ok:
            self._power_on = True
        return ok

    def turn_off(self) -> bool:
        ok = self._http_post_json("/json/state", {"on": False})
        if ok:
            self._power_on = False
            self._last_color = None  # force a resend after the next power-on
        return ok

    def query_power(self) -> Optional[bool]:
        state = self._http_get_json("/json/state")
        if state is None or "on" not in state:
            return None
        self._power_on = bool(state["on"])
        return self._power_on

    def ensure_on(self) -> bool:
        state = self.query_power()
        if state is None:
            state = self._power_on
        if state:
            return True
        return self.turn_on()

    # ------------------------------------------------------------------
    # Output (realtime UDP)
    # ------------------------------------------------------------------

    def set_rgb(self, r: int, g: int, b: int) -> bool:
        """Fill the whole strip with one colour over realtime UDP.

        Uses the same path as :meth:`set_pixels` (not the HTTP API) so effect
        modes that call this every frame stay fast. Dedupes + rate-limits like
        the MagicHome driver."""
        color = (r & 0xFF, g & 0xFF, b & 0xFF)
        if color == self._last_color:
            return True
        now = time.monotonic()
        if now - self._last_send_time < self._min_update_interval:
            return True

        ok = self._send_realtime([color] * max(1, self.led_count))
        if ok:
            self._last_color = color
            self._last_send_time = now
            self._power_on = True
        return ok

    def set_pixels(self, pixels: "list[tuple[int, int, int]]") -> bool:
        """Send per-LED colours over realtime UDP (DRGB / chunked DNRGB)."""
        now = time.monotonic()
        if now - self._last_send_time < self._min_update_interval:
            return True
        ok = self._send_realtime(pixels)
        if ok:
            self._last_send_time = now
            self._power_on = True
        return ok

    def _send_realtime(self, pixels: "list[tuple[int, int, int]]") -> bool:
        """Encode + send realtime packets; reconnect (HTTP info) on a backoff
        when we're not connected so ``is_connected``/``led_count`` recover."""
        if not self._connected:
            self._maybe_reconnect()
        try:
            self._ensure_socket()
            for pkt in build_realtime_packets(pixels):
                self._udp.sendto(pkt, (self._ip, self._realtime_port))  # type: ignore[union-attr]
            return True
        except OSError as exc:
            logger.warning("[WLED] Realtime send to %s failed: %s", self._ip, exc)
            self._connected = False
            return False

    # ------------------------------------------------------------------
    # Reconnect (capped exponential back-off, mirrors MagicHome)
    # ------------------------------------------------------------------

    def _current_backoff(self) -> float:
        backoff = self._reconnect_interval * (2 ** self._reconnect_failures)
        return min(backoff, self._reconnect_backoff_max)

    def _maybe_reconnect(self) -> bool:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._current_backoff():
            return False
        self._last_reconnect_attempt = now
        if self.connect():
            return True
        self._reconnect_failures += 1
        return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ip(self) -> str:
        return self._ip

    @ip.setter
    def ip(self, value: str) -> None:
        if value != self._ip:
            logger.info("[WLED] IP changed: %s → %s", self._ip, value)
            self._ip = value
            self._connected = False

    @property
    def is_addressable(self) -> bool:
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def power_on(self) -> Optional[bool]:
        return self._power_on

    @property
    def last_color(self) -> Optional[tuple[int, int, int]]:
        return self._last_color

    def __repr__(self) -> str:
        return f"WledDriver(ip={self._ip!r}, leds={self.led_count}, connected={self._connected})"
