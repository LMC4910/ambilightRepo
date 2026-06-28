"""
Windows notification listener
=============================
Uses the official ``Windows.UI.Notifications.Management.UserNotificationListener``
WinRT API (via the ``winsdk`` package). Crucially this API keeps delivering
notifications even when their banners are suppressed — fullscreen, Focus Assist /
Do Not Disturb, or a locked screen — which is exactly when the user misses them.

Phone notifications forwarded by **Phone Link** arrive here as notifications from
the Phone Link app; the originating app (Instagram, WhatsApp, …) can only be
guessed from the visual text, which the service layer does via keyword rules.

We poll ``get_notifications_async`` on a short interval rather than subscribing to
the change event — polling is markedly more robust across ``winsdk`` versions and
COM-apartment quirks, at a negligible cost for the ~1 s cadence.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
from typing import Optional

from .base import NotificationEvent, NotificationListener

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0   # seconds between notification queries


def _winsdk_available() -> bool:
    try:
        return importlib.util.find_spec("winsdk") is not None
    except Exception:
        return False


class WindowsNotificationListener(NotificationListener):
    source = "windows"

    def __init__(self, on_notification, loop=None) -> None:
        super().__init__(on_notification, loop)
        self._seen: set[int] = set()
        self._access: Optional[str] = None
        # Diagnostics: the distinct app names currently in the Action Center, only
        # re-logged when the set changes (so the in-app log shows what the OS is
        # actually surfacing without spamming every poll), plus a per-id label
        # cache so we don't re-read app_info over COM every second.
        self._last_present: set[str] = set()
        self._label_cache: dict[int, str] = {}

    # --- availability / permission ---------------------------------------
    @staticmethod
    def is_available() -> bool:
        import sys
        return sys.platform == "win32" and _winsdk_available()

    def permission_status(self) -> str:
        if not self.is_available():
            return "unavailable"
        try:
            from winsdk.windows.ui.notifications.management import (
                UserNotificationListener, UserNotificationListenerAccessStatus,
            )
            listener = UserNotificationListener.current
            status = _await(listener.request_access_async())
            if status == UserNotificationListenerAccessStatus.ALLOWED:
                return "granted"
            if status == UserNotificationListenerAccessStatus.DENIED:
                return "denied"
            return "unknown"
        except Exception as exc:
            logger.debug("[Notify] permission probe failed: %s", exc)
            return "unknown"

    # --- poll loop --------------------------------------------------------
    def _run_loop(self) -> None:
        try:
            from winsdk.windows.ui.notifications.management import (
                UserNotificationListener, UserNotificationListenerAccessStatus,
            )
            from winsdk.windows.ui.notifications import NotificationKinds
        except Exception as exc:
            logger.warning("[Notify] winsdk import failed; listener disabled: %s", exc)
            return

        listener = UserNotificationListener.current
        try:
            access = _await(listener.request_access_async())
            self._access = str(access)
            if access != UserNotificationListenerAccessStatus.ALLOWED:
                logger.warning(
                    "[Notify] Notification access not granted (%s). Enable it under "
                    "Settings → Privacy → Notifications.", access,
                )
                return
        except Exception as exc:
            logger.warning("[Notify] request_access failed: %s", exc)
            return

        # Seed the seen-set with the current backlog so we don't replay old
        # notifications on startup.
        try:
            existing = _await(listener.get_notifications_async(NotificationKinds.TOAST))
            seeded_labels: set[str] = set()
            for n in existing:
                self._seen.add(n.id)
                lbl = self._label_for(n)
                if lbl:
                    seeded_labels.add(lbl)
            logger.info(
                "[Notify] Seeded %d existing toast(s) at startup%s.",
                len(self._seen),
                f" from: {', '.join(sorted(seeded_labels))}" if seeded_labels else "",
            )
        except Exception as exc:
            logger.warning("[Notify] initial backlog read failed: %s", exc)

        while not self._stop.wait(_POLL_INTERVAL):
            try:
                self._poll_once(listener, NotificationKinds.TOAST)
            except Exception as exc:  # keep the thread alive across hiccups
                logger.debug("[Notify] poll error: %s", exc)

    def _poll_once(self, listener, toast_kind) -> None:
        notifications = _await(listener.get_notifications_async(toast_kind))
        current_ids = set()
        present_labels: set[str] = set()
        for n in notifications:
            current_ids.add(n.id)
            label = self._label_for(n)
            if label:
                present_labels.add(label)
            if n.id in self._seen:
                continue
            self._seen.add(n.id)
            event = self._to_event(n)
            if event is not None:
                logger.info(
                    "[Notify] Toast detected: app=%s id=%s -> emitting.",
                    event.app_name or event.app_id, n.id,
                )
                self._emit(event)
            else:
                logger.warning(
                    "[Notify] Toast id=%s from %s dropped (no usable app name or text).",
                    n.id, label or "<unknown>",
                )
        # Visibility into what the OS actually surfaces — the decisive signal for
        # "why doesn't app X flash". Only logged when the set changes.
        if present_labels != self._last_present:
            logger.info(
                "[Notify] Toasts currently in Action Center: %s",
                ", ".join(sorted(present_labels)) or "<none>",
            )
            self._last_present = present_labels
        # Drop ids that are no longer present so the set can't grow unbounded.
        # Intersect unconditionally: when the active list is empty we must clear
        # stale ids too, otherwise a reused WinRT id could be suppressed later.
        self._seen &= current_ids
        # Keep the label cache bounded to live ids for the same reason.
        if self._label_cache:
            self._label_cache = {k: v for k, v in self._label_cache.items() if k in current_ids}

    def _label_for(self, n) -> str:
        """Best-effort app display name for *n*, cached by id to avoid re-reading
        app_info over COM on every poll. Empty string when unavailable."""
        nid = n.id
        lbl = self._label_cache.get(nid)
        if lbl is None:
            try:
                lbl = n.app_info.display_info.display_name or ""
            except Exception:
                lbl = ""
            self._label_cache[nid] = lbl
        return lbl

    def _to_event(self, n) -> Optional[NotificationEvent]:
        import time
        app_name = ""
        app_id = ""
        icon_bytes = None
        title = ""
        body = ""
        try:
            info = n.app_info
            display = info.display_info
            app_name = display.display_name or ""
            try:
                app_id = info.app_user_model_id or ""
            except Exception:
                app_id = ""
            icon_bytes = _read_logo(display)
        except Exception as exc:
            logger.info("[Notify] app_info read failed (id=%s): %s", getattr(n, "id", "?"), exc)

        try:
            texts = []
            binding = n.notification.visual.bindings
            for b in binding:
                for el in b.get_text_elements():
                    if el.text:
                        texts.append(el.text)
            if texts:
                title = texts[0]
                body = " ".join(texts[1:])
        except Exception as exc:
            logger.info("[Notify] visual text read failed (id=%s): %s", getattr(n, "id", "?"), exc)

        if not app_id:
            app_id = app_name.lower()
        if not (app_name or title or body):
            return None
        return NotificationEvent(
            app_id=app_id, app_name=app_name, title=title, body=body,
            icon_bytes=icon_bytes, source=self.source, received_at=time.monotonic(),
        )


def _read_logo(display) -> Optional[bytes]:
    """Read the app logo stream into PNG/icon bytes, or ``None``."""
    try:
        from winsdk.windows.foundation import Size
        from winsdk.windows.storage.streams import (
            DataReader, InputStreamOptions,
        )
        ref = display.get_logo(Size(64, 64))
        if ref is None:
            return None
        stream = _await(ref.open_read_async())
        size = stream.size
        if not size:
            return None
        reader = DataReader(stream.get_input_stream_at(0))
        _await(reader.load_async(size))
        buf = bytearray(size)
        reader.read_bytes(buf)
        return bytes(buf)
    except Exception as exc:
        logger.debug("[Notify] logo read failed: %s", exc)
        return None


_tls = threading.local()


async def _drive(async_op):
    return await async_op


def _await(async_op):
    """Block on a WinRT IAsyncOperation/IAsyncAction and return its result.

    ``winsdk`` async ops are awaitable but expose no synchronous ``.get()``. We
    drive them on a per-thread asyncio loop — both the listener daemon thread and
    the executor thread used by the permission probe get their own loop, created
    lazily and reused.
    """
    loop = getattr(_tls, "loop", None)
    if loop is None:
        loop = asyncio.new_event_loop()
        _tls.loop = loop
    return loop.run_until_complete(_drive(async_op))
