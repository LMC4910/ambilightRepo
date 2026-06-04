"""
Foreground application detection (FR-PROF-07)
=============================================
Returns the executable name of the currently focused window, used by the
auto-profile switcher to map apps → profiles.

Windows: GetForegroundWindow → GetWindowThreadProcessId → QueryFullProcessImageNameW
(pointer-sized ctypes signatures to stay 64-bit-safe — see the same care taken in
``platform_monitor.py``). Other platforms return ``None`` for now (the switcher
simply never matches a rule and leaves the profile unchanged).
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _get_foreground_app_windows() -> str | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)


def get_foreground_app() -> str | None:
    """Lowercased exe basename of the focused window (e.g. ``"chrome.exe"``), or None."""
    try:
        if sys.platform == "win32":
            return _get_foreground_app_windows()
    except Exception as exc:  # pragma: no cover - platform/edge cases
        logger.debug("[Foreground] detection failed: %s", exc)
    return None
