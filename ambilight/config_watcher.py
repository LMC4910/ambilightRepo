"""
Config File Watcher (migration Task 1.5.1)
==========================================
Watches the active ``configuration.yaml`` and, on change, reloads it and emits a
``CONFIG_UPDATE`` event on the bus — the same event the API's ``PUT /config``
publishes, which the :class:`PipelineController` already handles. Editing the
YAML on disk therefore hot-reloads the running pipeline without a restart.

Uses ``watchdog`` when installed; otherwise falls back to a lightweight mtime
polling thread so hot-reload works without the optional dependency.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from .config import ConfigManager
from .events import bus

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 0.5


class ConfigWatcher:
    def __init__(self, path: str, loop: asyncio.AbstractEventLoop) -> None:
        self._path = Path(path).resolve()
        self._loop = loop
        self._observer = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_reload = 0.0

    def start(self) -> None:
        self._running = True
        if self._start_watchdog():
            logger.info("[ConfigWatcher] Watching %s (watchdog)", self._path)
        else:
            self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="ConfigWatcherPoll")
            self._poll_thread.start()
            logger.info("[ConfigWatcher] Watching %s (mtime polling)", self._path)

    def _start_watchdog(self) -> bool:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            return False

        watcher = self
        target_name = self._path.name

        class _Handler(FileSystemEventHandler):
            def _maybe(self, event_path: str) -> None:
                if os.path.basename(event_path) == target_name:
                    watcher._reload()

            def on_modified(self, event):
                if not event.is_directory:
                    self._maybe(event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    self._maybe(event.src_path)

            def on_moved(self, event):
                self._maybe(getattr(event, "dest_path", "") or "")

        self._observer = Observer()
        self._observer.schedule(_Handler(), str(self._path.parent), recursive=False)
        self._observer.start()
        return True

    def _poll_loop(self) -> None:
        last_mtime = self._mtime()
        while self._running:
            time.sleep(1.0)
            m = self._mtime()
            if m is not None and m != last_mtime:
                last_mtime = m
                self._reload()

    def _mtime(self) -> Optional[float]:
        try:
            return self._path.stat().st_mtime
        except OSError:
            return None

    def _reload(self) -> None:
        now = time.monotonic()
        if now - self._last_reload < _DEBOUNCE_S:
            return
        self._last_reload = now
        try:
            cfg = ConfigManager.load(str(self._path))
            asyncio.run_coroutine_threadsafe(bus.publish("CONFIG_UPDATE", cfg), self._loop)
            logger.info("[ConfigWatcher] Reloaded config and published CONFIG_UPDATE.")
        except Exception as exc:
            logger.warning("[ConfigWatcher] Reload failed: %s", exc)

    def stop(self) -> None:
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None
