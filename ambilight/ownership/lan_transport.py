"""
LAN UDP ownership transport
===========================
Fallback coordination channel when no MQTT broker is configured. Each instance
broadcasts its full claim list on a dedicated UDP port every heartbeat and
listens for everyone else's. No broker, no extra dependencies — mirrors the
socket recipe in :func:`ambilight.discovery._udp_discover`.

The wire format is a single JSON datagram per announcement::

    {"magic": "ambilight-ownership-v1",
     "instance_id": "...", "instance_label": "Living-Room-PC",
     "ts": 1782236852.4, "claims": [{"device_key": "magichome:30:3a:...",
                                     "priority": 0, "claimed_at": 1782236800.1}]}
"""

from __future__ import annotations

import json
import logging
import socket
import threading

logger = logging.getLogger(__name__)

# Bumped if the announcement schema ever changes incompatibly.
_MAGIC = "ambilight-ownership-v1"
_RECV_BUF = 8192


class LanTransport:
    """UDP broadcast/listen transport for ownership announcements."""

    def __init__(self, port: int, on_remote) -> None:
        self._port = int(port)
        self._on_remote = on_remote
        self._stop = threading.Event()
        self._rx_thread: "threading.Thread | None" = None
        self._send_sock: "socket.socket | None" = None

    def start(self) -> bool:
        self._stop.clear()
        self._rx_thread = threading.Thread(
            target=self._listen, name="ownership-lan-rx", daemon=True
        )
        self._rx_thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        sock = self._send_sock
        self._send_sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def publish(self, announcement: dict) -> None:
        """Broadcast *announcement* to the LAN (best effort)."""
        try:
            if self._send_sock is None:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._send_sock = s
            data = json.dumps({"magic": _MAGIC, **announcement}).encode("utf-8")
            self._send_sock.sendto(data, ("255.255.255.255", self._port))
        except OSError as exc:
            logger.debug("[Ownership LAN] send failed: %s", exc)

    def _listen(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # SO_REUSEPORT lets a second local instance bind the same port (Unix);
            # Windows has no equivalent (SO_REUSEADDR already shares), so ignore it.
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            sock.settimeout(0.5)
            sock.bind(("", self._port))
        except OSError as exc:
            logger.warning("[Ownership LAN] cannot bind UDP %d: %s", self._port, exc)
            return
        while not self._stop.is_set():
            try:
                data, _addr = sock.recvfrom(_RECV_BUF)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8", errors="replace"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict) or msg.get("magic") != _MAGIC:
                continue
            try:
                self._on_remote(msg)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[Ownership LAN] handler error: %s", exc)
        try:
            sock.close()
        except OSError:
            pass
