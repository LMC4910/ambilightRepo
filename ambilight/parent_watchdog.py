"""
Parent-process watchdog (force-quit cleanup)
============================================
When the Electron shell spawns the background service it passes its own PID via
``AMBILIGHT_PARENT_PID``. If the shell is **force-quit** — Task Manager "End
task", the Windows 11 taskbar "End task", a crash, or any kill that runs no
graceful handler — the service would otherwise be orphaned: LEDs frozen, the
API port held, a stray process in the tray-less background.

This watchdog polls the parent PID and, the moment it disappears, triggers a
clean service shutdown (which turns the strip off and releases the port). It is
a no-op when the env var is absent — e.g. a manually started service the shell
merely *adopted* must not be torn down when the shell exits.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

PARENT_PID_ENV = "AMBILIGHT_PARENT_PID"


def _pid_alive(pid: int) -> bool:
    """Return True while process *pid* is still running.

    Cross-platform: ``WaitForSingleObject`` on Windows (unambiguous — avoids the
    ``STILL_ACTIVE`` exit-code edge case), ``os.kill(pid, 0)`` on POSIX. Errors
    bias toward *alive* so a transient query failure never falsely tears the
    service down; only a definitive "process not found" reports dead.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x00000102       # still running
        ERROR_INVALID_PARAMETER = 87    # no such PID
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            # No handle: dead only if the PID is genuinely unknown; otherwise
            # (e.g. access denied) assume alive.
            return kernel32.GetLastError() != ERROR_INVALID_PARAMETER
        try:
            return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def start_parent_watchdog(
    on_parent_exit: Callable[[], None],
    poll_interval: float = 1.0,
) -> Optional[threading.Thread]:
    """Start a daemon thread that calls *on_parent_exit* when the parent dies.

    Reads the parent PID from ``AMBILIGHT_PARENT_PID``. Returns the started
    thread, or ``None`` when no (valid) parent PID is configured.
    """
    raw = os.environ.get(PARENT_PID_ENV, "").strip()
    if not raw:
        return None
    try:
        ppid = int(raw)
    except ValueError:
        logger.warning("[Watchdog] Invalid %s=%r; parent watchdog disabled.", PARENT_PID_ENV, raw)
        return None
    if ppid <= 0 or ppid == os.getpid():
        return None

    def _run() -> None:
        logger.info("[Watchdog] Watching parent PID %d; service will stop if it exits.", ppid)
        while True:
            if not _pid_alive(ppid):
                logger.warning("[Watchdog] Parent %d is gone — shutting down the service.", ppid)
                try:
                    on_parent_exit()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("[Watchdog] shutdown callback failed: %s; forcing exit.", exc)
                    os._exit(0)
                return
            time.sleep(poll_interval)

    thread = threading.Thread(target=_run, name="parent-watchdog", daemon=True)
    thread.start()
    return thread
