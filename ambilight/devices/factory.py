"""
Driver factory (A0)
===================
Builds the right :class:`LedDriver` from a device spec's ``protocol`` field, so
the pipeline never hard-codes a protocol. Unknown/missing protocols fall back to
MagicHome (the historical default) with a warning, preserving back-compat for
configs written before ``protocol`` existed.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import LedDriver

logger = logging.getLogger(__name__)


def create_driver(spec: dict[str, Any]) -> LedDriver:
    """Instantiate an :class:`LedDriver` for ``spec``.

    Recognised ``spec`` keys (all optional except ``ip``): ``protocol``, ``ip``,
    ``port``, ``connect_timeout``, ``send_timeout``, ``reconnect_interval``,
    ``min_update_interval``, ``reconnect_backoff_max``, ``kind``, ``led_count``.
    """
    protocol = str(spec.get("protocol") or "magichome").strip().lower()

    common = dict(
        ip=spec.get("ip", ""),
        connect_timeout=float(spec.get("connect_timeout", 2.0)),
        send_timeout=float(spec.get("send_timeout", 1.0)),
        reconnect_interval=float(spec.get("reconnect_interval", 5.0)),
        min_update_interval=float(spec.get("min_update_interval", 0.033)),
        reconnect_backoff_max=float(spec.get("reconnect_backoff_max", 30.0)),
        led_count=int(spec.get("led_count", 30)),
    )

    if protocol == "wled":
        from .wled import WledDriver
        # `port` is WLED's HTTP/JSON API port (default 80); the realtime UDP port
        # is fixed at 21324. 5577 is the MagicHome TCP port AND the legacy
        # device.port default, so a WLED spec that inherited it (any caller that
        # doesn't pre-resolve the port) must fall back to 80 rather than probe
        # http://<ip>:5577/json/info — this keeps the factory safe on its own.
        try:
            raw_port = int(spec.get("port") or 0)
        except (TypeError, ValueError):
            raw_port = 0
        http_port = raw_port if raw_port and raw_port != 5577 else 80
        return WledDriver(port=http_port, **common)

    if protocol != "magichome":
        logger.warning(
            "[Devices] Unknown protocol %r for %s; falling back to MagicHome.",
            protocol, spec.get("ip", "?"),
        )
    from .magichome import MagicHomeController
    return MagicHomeController(
        port=int(spec.get("port", 5577)),
        kind=spec.get("kind", "single"),
        **common,
    )
