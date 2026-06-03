"""
Platform Monitor Module
=======================
Monitors OS-level display and power events to automatically pause/resume
the capture pipeline when displays turn off, the system sleeps, or the user locks
the session — and to rebuild capture when the monitor topology changes
(connect/disconnect/resolution change).

Events published to the EventBus:
    DISPLAY_OFF / DISPLAY_ON       — session lock / unlock, screensaver
    SYSTEM_SUSPEND / SYSTEM_RESUME — sleep / wake
    DISPLAY_CHANGED                — monitor connect/disconnect/resolution change

This preserves system resources and prevents capture backends (especially WGC)
from crashing when the display compositor is suspended or reconfigured.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import threading
from abc import ABC, abstractmethod
from typing import Optional

from .events import bus

logger = logging.getLogger(__name__)


class DisplayMonitor(ABC):
    """Abstract base class for OS-specific display monitoring."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop_safe, daemon=True, name=f"{self.__class__.__name__}Thread")
        self._thread.start()
        logger.info("[%s] Started", self.__class__.__name__)

    def stop(self) -> None:
        self._running = False
        # The thread should be implemented to check self._running periodically or be a daemon

    def _run_loop_safe(self) -> None:
        """Wrap the OS loop so a failure can't take down the thread silently."""
        try:
            self._run_loop()
        except Exception as exc:
            logger.exception("[%s] Monitor loop crashed: %s", self.__class__.__name__, exc)

    @abstractmethod
    def _run_loop(self) -> None:
        """OS-specific blocking loop running in a background thread."""

    def _publish_event(self, event_type: str) -> None:
        """Helper to publish an event back to the main asyncio loop thread-safely."""
        logger.info("[PlatformMonitor] Triggering %s", event_type)
        asyncio.run_coroutine_threadsafe(bus.publish(event_type), self._loop)


class WindowsDisplayMonitor(DisplayMonitor):
    """
    Windows-specific monitor using User32 / WTSAPI32.

    Listens for session lock/unlock, system suspend/resume, and display
    topology changes (WM_DISPLAYCHANGE).

    Note
    ----
    ctypes argtypes/restypes are declared explicitly: on 64-bit Windows, window
    handles and module handles are pointer-sized, and the default ctypes ``int``
    marshalling truncates / overflows them (the cause of the historical
    "int too long to convert" crash in CreateWindowExW).
    """
    def _run_loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        import time

        # Pointer-sized integer types for 64-bit safety
        LRESULT = ctypes.c_ssize_t
        WPARAM = ctypes.c_size_t   # UINT_PTR
        LPARAM = ctypes.c_ssize_t  # LONG_PTR
        HWND = wintypes.HWND       # c_void_p
        HMODULE = wintypes.HMODULE

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

        # Message constants
        WM_POWERBROADCAST = 0x0218
        PBT_APMRESUMEAUTOMATIC = 0x0012
        PBT_APMSUSPEND = 0x0004
        WM_WTSSESSION_CHANGE = 0x02B1
        WTS_SESSION_LOCK = 0x7
        WTS_SESSION_UNLOCK = 0x8
        WM_DISPLAYCHANGE = 0x007E
        WM_QUIT = 0x0012

        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, ctypes.c_uint, WPARAM, LPARAM)

        # Declare signatures (handles are pointer-sized!)
        user32.DefWindowProcW.argtypes = [HWND, ctypes.c_uint, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = HMODULE
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.restype = HWND
        wtsapi32.WTSRegisterSessionNotification.argtypes = [HWND, wintypes.DWORD]
        wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL
        wtsapi32.WTSUnRegisterSessionNotification.argtypes = [HWND]
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_POWERBROADCAST:
                if wparam == PBT_APMSUSPEND:
                    self._publish_event("SYSTEM_SUSPEND")
                elif wparam == PBT_APMRESUMEAUTOMATIC:
                    self._publish_event("SYSTEM_RESUME")
            elif msg == WM_WTSSESSION_CHANGE:
                if wparam == WTS_SESSION_LOCK:
                    self._publish_event("DISPLAY_OFF")
                elif wparam == WTS_SESSION_UNLOCK:
                    self._publish_event("DISPLAY_ON")
            elif msg == WM_DISPLAYCHANGE:
                self._publish_event("DISPLAY_CHANGED")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ('style', ctypes.c_uint),
                ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR),
            ]

        # Keep a strong reference to the callback so it is not garbage-collected.
        self._wndproc_ref = WNDPROC(wndproc)

        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.lpszClassName = "AmbilightPlatformMonitor"
        wndclass.hInstance = kernel32.GetModuleHandleW(None)

        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        if not user32.RegisterClassW(ctypes.byref(wndclass)):
            # Class may already be registered from a previous start — continue.
            logger.debug("[WindowsDisplayMonitor] RegisterClassW returned 0 (err=%s)", ctypes.get_last_error())

        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
        ]
        hwnd = user32.CreateWindowExW(
            0, wndclass.lpszClassName, "AmbilightPlatformMonitorWindow",
            0, 0, 0, 0, 0, None, None, wndclass.hInstance, None
        )
        if not hwnd:
            raise OSError(f"CreateWindowExW failed (err={ctypes.get_last_error()})")

        # Register for session (lock/unlock) notifications
        NOTIFY_FOR_THIS_SESSION = 0
        wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION)

        # Message loop
        msg = wintypes.MSG()
        try:
            while self._running:
                ret = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE
                if ret != 0:
                    if msg.message == WM_QUIT:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.1)
        finally:
            wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            user32.DestroyWindow.argtypes = [HWND]
            user32.DestroyWindow(hwnd)


class MacOSDisplayMonitor(DisplayMonitor):
    """
    macOS-specific monitor using NSWorkspace (sleep/lock) and Quartz
    CGDisplayRegisterReconfigurationCallback (monitor topology changes).
    """
    def _run_loop(self) -> None:
        try:
            from AppKit import NSWorkspace, NSObject  # type: ignore
            from Foundation import NSRunLoop, NSDate  # type: ignore
        except ImportError:
            logger.error("macOS monitor requires pyobjc. Pip install pyobjc.")
            return

        class SleepObserver(NSObject):
            def receiveSleepNotification_(self, notification):
                self._monitor._publish_event("SYSTEM_SUSPEND")
                self._monitor._publish_event("DISPLAY_OFF")

            def receiveWakeNotification_(self, notification):
                self._monitor._publish_event("SYSTEM_RESUME")
                self._monitor._publish_event("DISPLAY_ON")

            def receiveScreenIsLockedNotification_(self, notification):
                self._monitor._publish_event("DISPLAY_OFF")

            def receiveScreenIsUnlockedNotification_(self, notification):
                self._monitor._publish_event("DISPLAY_ON")

        observer = SleepObserver.new()
        observer._monitor = self

        workspace = NSWorkspace.sharedWorkspace()
        nc = workspace.notificationCenter()

        nc.addObserver_selector_name_object_(observer, "receiveSleepNotification:", "NSWorkspaceWillSleepNotification", None)
        nc.addObserver_selector_name_object_(observer, "receiveWakeNotification:", "NSWorkspaceDidWakeNotification", None)
        nc.addObserver_selector_name_object_(observer, "receiveScreenIsLockedNotification:", "com.apple.screenIsLocked", None)
        nc.addObserver_selector_name_object_(observer, "receiveScreenIsUnlockedNotification:", "com.apple.screenIsUnlocked", None)

        # Monitor connect/disconnect/resolution changes via Quartz.
        try:
            import Quartz  # type: ignore

            def _reconfig_cb(display, flags, user_info):
                # Fire on add/remove/desktop-shape changes; ignore begin-config.
                relevant = (
                    Quartz.kCGDisplayAddFlag
                    | Quartz.kCGDisplayRemoveFlag
                    | Quartz.kCGDisplayDesktopShapeChangedFlag
                )
                if flags & relevant:
                    self._publish_event("DISPLAY_CHANGED")

            # Keep a strong reference so the callback is not collected.
            self._reconfig_cb_ref = _reconfig_cb
            Quartz.CGDisplayRegisterReconfigurationCallback(_reconfig_cb, None)
        except Exception as exc:
            logger.warning("[MacOSDisplayMonitor] Display reconfig callback unavailable: %s", exc)

        run_loop = NSRunLoop.currentRunLoop()
        while self._running:
            run_loop.runMode_beforeDate_("NSDefaultRunLoopMode", NSDate.dateWithTimeIntervalSinceNow_(0.5))


class LinuxDisplayMonitor(DisplayMonitor):
    """
    Linux-specific monitor using dbus for logind / screensaver events and
    (optionally) pyudev for DRM connector hotplug (monitor connect/disconnect).
    """
    def _run_loop(self) -> None:
        try:
            import dbus # type: ignore
            from dbus.mainloop.glib import DBusGMainLoop # type: ignore
            from gi.repository import GLib # type: ignore
        except ImportError:
            logger.error("Linux monitor requires dbus-python and PyGObject.")
            return

        DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        session_bus = dbus.SessionBus()

        def handle_sleep(sleeping):
            if sleeping:
                self._publish_event("SYSTEM_SUSPEND")
                self._publish_event("DISPLAY_OFF")
            else:
                self._publish_event("SYSTEM_RESUME")
                self._publish_event("DISPLAY_ON")

        def handle_screen_lock(active):
            if active:
                self._publish_event("DISPLAY_OFF")
            else:
                self._publish_event("DISPLAY_ON")

        # Systemd sleep
        bus.add_signal_receiver(
            handle_sleep,
            signal_name="PrepareForSleep",
            dbus_interface="org.freedesktop.login1.Manager",
            bus_name="org.freedesktop.login1"
        )

        # GNOME / KDE Screensaver
        try:
            session_bus.add_signal_receiver(
                handle_screen_lock,
                signal_name="ActiveChanged",
                dbus_interface="org.freedesktop.ScreenSaver"
            )
        except Exception:
            pass

        # DRM connector hotplug via udev (monitor connect/disconnect).
        try:
            import pyudev  # type: ignore

            context = pyudev.Context()
            udev_monitor = pyudev.Monitor.from_netlink(context)
            udev_monitor.filter_by(subsystem="drm")

            def _udev_cb(action, device):  # observer thread callback
                # A "change" event on a drm card fires on connector hotplug.
                self._publish_event("DISPLAY_CHANGED")

            self._udev_observer = pyudev.MonitorObserver(udev_monitor, _udev_cb)
            self._udev_observer.start()
        except Exception as exc:
            logger.warning("[LinuxDisplayMonitor] udev DRM hotplug unavailable: %s", exc)

        loop = GLib.MainLoop()

        def check_exit():
            if not self._running:
                loop.quit()
            return True

        GLib.timeout_add(500, check_exit)
        loop.run()


def get_platform_monitor(loop: asyncio.AbstractEventLoop) -> DisplayMonitor:
    """Factory to return the appropriate monitor for the current OS."""
    sys_plat = platform.system()
    if sys_plat == "Windows":
        return WindowsDisplayMonitor(loop)
    elif sys_plat == "Darwin":
        return MacOSDisplayMonitor(loop)
    elif sys_plat == "Linux":
        return LinuxDisplayMonitor(loop)
    else:
        logger.warning("Unsupported platform '%s' for DisplayMonitor. Using dummy monitor.", sys_plat)

        # Dummy fallback
        class DummyMonitor(DisplayMonitor):
            def _run_loop(self) -> None:
                import time
                while self._running:
                    time.sleep(1)
        return DummyMonitor(loop)
