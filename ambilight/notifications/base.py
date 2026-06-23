"""
Notification listener interface
===============================
Shared data model and abstract base for the per-OS notification listeners that
drive the Notification Flash feature.

A listener runs a background daemon thread in the **API/service process** (never
the pipeline process — it has no device access). When it sees a notification it
hands a :class:`NotificationEvent` to its ``on_notification`` callback. The
callback is invoked *from the listener thread*, so implementations marshal it
back onto the asyncio loop via :func:`asyncio.run_coroutine_threadsafe`, mirroring
the ``DisplayMonitor`` pattern in ``platform_monitor.py``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class NotificationEvent:
    """A single OS notification, normalised across platforms."""
    app_id: str                 # stable key: AUMID / bundle id (cache key)
    app_name: str               # human display name ("Discord", "Phone Link")
    title: str                  # notification title text
    body: str                   # notification body text
    icon_bytes: Optional[bytes] # raw icon/logo image bytes, if the OS provided one
    source: str                 # "windows" | "darwin"
    received_at: float          # time.monotonic() when observed


# A callback that receives a NotificationEvent. Invoked on the listener thread.
OnNotification = Callable[[NotificationEvent], None]


class NotificationListener(ABC):
    """Abstract background listener for OS notifications.

    Subclasses implement :meth:`_run_loop` (the blocking poll body) plus the
    availability/permission probes. ``start``/``stop`` manage the daemon thread.
    """

    source = "base"

    def __init__(self, on_notification: OnNotification,
                 loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._on_notification = on_notification
        self._loop = loop
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not self.is_available():
            logger.info("[Notify] %s listener unavailable; not starting.", self.source)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop_safe, name=f"NotifyListener-{self.source}", daemon=True,
        )
        self._thread.start()
        logger.info("[Notify] %s listener started.", self.source)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            # Only drop the reference once the thread has actually exited; keeping
            # it while still alive lets start() detect the live thread and refuse
            # to spawn a duplicate listener (which would double-deliver events).
            if not self._thread.is_alive():
                self._thread = None

    # --- helpers for subclasses ------------------------------------------
    def _emit(self, event: NotificationEvent) -> None:
        """Deliver an event to the callback, safely hopping to the asyncio loop."""
        try:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._on_notification, event)
            else:
                self._on_notification(event)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[Notify] emit failed: %s", exc)

    def _run_loop_safe(self) -> None:
        """Wrap :meth:`_run_loop` so a crash logs instead of killing silently."""
        try:
            self._run_loop()
        except Exception as exc:  # pragma: no cover - platform/edge cases
            logger.warning("[Notify] %s listener loop crashed: %s", self.source, exc)

    # --- abstract surface -------------------------------------------------
    @abstractmethod
    def _run_loop(self) -> None:
        """Blocking poll body; should return promptly when ``self._stop`` is set."""

    @abstractmethod
    def permission_status(self) -> str:
        """One of ``granted`` | ``denied`` | ``unknown`` | ``unavailable``."""

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """True when this listener can run on the current machine."""


def get_notification_listener(
    on_notification: OnNotification,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[NotificationListener]:
    """Return the listener for the current platform, or ``None`` if unsupported."""
    try:
        if sys.platform == "win32":
            from .windows import WindowsNotificationListener
            listener = WindowsNotificationListener(on_notification, loop)
        elif sys.platform == "darwin":
            from .darwin import DarwinNotificationListener
            listener = DarwinNotificationListener(on_notification, loop)
        else:
            return None
    except Exception as exc:  # pragma: no cover - import/platform issues
        logger.info("[Notify] No notification listener for this platform: %s", exc)
        return None
    if not listener.is_available():
        return None
    return listener
