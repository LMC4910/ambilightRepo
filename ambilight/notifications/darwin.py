"""
macOS notification listener (best-effort, fragile)
==================================================
macOS exposes **no public API** to observe other apps' notifications. This
listener polls Apple's private Notification Center SQLite database, which:

  * requires the app to be granted **Full Disk Access**, and
  * relies on an undocumented schema that Apple can change in any macOS update.

It is therefore best-effort: on any failure it logs a warning and degrades to a
no-op rather than crashing the service. The DB is opened read-only / immutable so
we never lock or corrupt Notification Center.
"""

from __future__ import annotations

import logging
import os
import plistlib
import sqlite3
import time
from typing import Optional

from .base import NotificationEvent, NotificationListener

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.5  # seconds


def _candidate_db_paths() -> list[str]:
    home = os.path.expanduser("~")
    paths = [
        os.path.join(home, "Library", "Group Containers",
                     "group.com.apple.usernotifications", "db2", "db"),
        os.path.join(home, "Library", "Group Containers",
                     "group.com.apple.usernotifications", "db", "db"),
    ]
    # Modern macOS keeps the DB under the per-user DARWIN_USER_DIR.
    try:
        import subprocess
        base = subprocess.run(
            ["getconf", "DARWIN_USER_DIR"], capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if base:
            paths.append(os.path.join(base, "com.apple.notificationcenter", "db2", "db"))
    except Exception:
        pass
    return paths


def _find_db() -> Optional[str]:
    for p in _candidate_db_paths():
        if os.path.exists(p):
            return p
    return None


class DarwinNotificationListener(NotificationListener):
    source = "darwin"

    def __init__(self, on_notification, loop=None) -> None:
        super().__init__(on_notification, loop)
        self._db_path = _find_db()
        self._last_rec_id = 0

    @staticmethod
    def is_available() -> bool:
        import sys
        return sys.platform == "darwin" and _find_db() is not None

    def permission_status(self) -> str:
        if not self._db_path:
            return "unavailable"
        try:
            conn = self._open()
            conn.close()
            return "granted"
        except sqlite3.OperationalError:
            # Almost always "unable to open database file" → Full Disk Access missing.
            return "denied"
        except Exception:
            return "unknown"

    def _open(self) -> sqlite3.Connection:
        # Read-only + immutable: never block on Notification Center's own writes.
        uri = f"file:{self._db_path}?mode=ro&immutable=1"
        return sqlite3.connect(uri, uri=True, timeout=1.0)

    def _run_loop(self) -> None:
        if not self._db_path:
            return
        logger.warning(
            "[Notify] macOS notification capture is best-effort: it reads Apple's "
            "private Notification Center DB and may break on OS updates."
        )
        # Seed last_rec_id so we don't replay history on startup.
        try:
            self._last_rec_id = self._max_rec_id()
        except Exception as exc:
            logger.warning("[Notify] cannot read Notification Center DB: %s", exc)
            return

        while not self._stop.wait(_POLL_INTERVAL):
            try:
                self._poll_once()
            except Exception as exc:
                logger.debug("[Notify] macOS poll error: %s", exc)

    def _max_rec_id(self) -> int:
        conn = self._open()
        try:
            cur = conn.execute("SELECT MAX(rec_id) FROM record")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()

    def _poll_once(self) -> None:
        conn = self._open()
        try:
            cur = conn.execute(
                "SELECT rec_id, app_id, data FROM record WHERE rec_id > ? ORDER BY rec_id",
                (self._last_rec_id,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        for rec_id, app_col, data in rows:
            self._last_rec_id = max(self._last_rec_id, int(rec_id))
            event = self._row_to_event(app_col, data)
            if event is not None:
                self._emit(event)

    def _row_to_event(self, app_col, data) -> Optional[NotificationEvent]:
        bundle_id = ""
        title = ""
        body = ""
        try:
            payload = plistlib.loads(bytes(data)) if data else {}
            req = payload.get("req", {}) if isinstance(payload, dict) else {}
            bundle_id = str(payload.get("app") or app_col or "")
            title = str(req.get("titl") or "")
            body = str(req.get("body") or "")
        except Exception as exc:
            logger.debug("[Notify] plist parse failed: %s", exc)
            bundle_id = str(app_col or "")

        if not (bundle_id or title or body):
            return None
        icon = _icon_for_bundle(bundle_id) if bundle_id else None
        return NotificationEvent(
            app_id=bundle_id, app_name=bundle_id, title=title, body=body,
            icon_bytes=icon, source=self.source, received_at=time.monotonic(),
        )


def _icon_for_bundle(bundle_id: str) -> Optional[bytes]:
    """Best-effort: resolve the app's icon (.icns) bytes via NSWorkspace (pyobjc)."""
    try:
        from AppKit import NSWorkspace  # type: ignore
        ws = NSWorkspace.sharedWorkspace()
        url = ws.URLForApplicationWithBundleIdentifier_(bundle_id)
        if url is None:
            return None
        app_path = url.path()
        # Read Info.plist → CFBundleIconFile, then the .icns in Resources.
        info_plist = os.path.join(app_path, "Contents", "Info.plist")
        icon_name = None
        if os.path.exists(info_plist):
            with open(info_plist, "rb") as fh:
                info = plistlib.load(fh)
            icon_name = info.get("CFBundleIconFile")
        if not icon_name:
            return None
        if not icon_name.endswith(".icns"):
            icon_name += ".icns"
        icns = os.path.join(app_path, "Contents", "Resources", icon_name)
        if not os.path.exists(icns):
            return None
        with open(icns, "rb") as fh:
            return fh.read()
    except Exception as exc:
        logger.debug("[Notify] macOS icon lookup failed: %s", exc)
        return None
