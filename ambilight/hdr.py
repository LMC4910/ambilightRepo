r"""
HDR display-state detection (G2)
================================
Reports, per 0-based monitor index, whether Windows **HDR / advanced color** is
currently *enabled* for that display. The pipeline uses this to decide whether a
captured frame needs tone-mapping back to SDR before colour analysis — HDR
content captured as-is looks washed-out and desaturated.

Mechanism (Windows 10 1709+):
  * ``EnumDisplayMonitors`` gives the GDI device name (``\\.\DISPLAY1`` …) for
    each monitor *in the same order the capture backends index by* — matching
    ``capture.monitor_index`` (see ``monitors.py``).
  * ``QueryDisplayConfig`` + ``DisplayConfigGetDeviceInfo`` map that GDI name to
    the display target's ``DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO``, whose
    ``advancedColorEnabled`` bit is HDR-on.

Off Windows (or if any Win32 call fails) every display reports SDR, so callers
degrade gracefully to "no tone-mapping".
"""

from __future__ import annotations

import logging
import sys
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# --- GDI device name per capture index -------------------------------------

def _gdi_names_by_index() -> List[str]:
    r"""Return GDI device names (``\\.\DISPLAY1`` …) ordered to match
    ``capture.monitor_index`` (the ``EnumDisplayMonitors`` order)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
    )
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    names: List[str] = []

    def _cb(hmon, _hdc, _lprc, _lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            names.append(str(mi.szDevice))
        return 1

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return names


# --- HDR state per GDI device name -----------------------------------------

def _hdr_by_gdi_name() -> Dict[str, bool]:
    r"""Map GDI device name (``\\.\DISPLAY1`` …) → HDR-enabled, via DISPLAYCONFIG."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    UINT32 = ctypes.c_uint32

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
        _fields_ = [("adapterId", LUID), ("id", UINT32),
                    ("modeInfoIdx", UINT32), ("statusFlags", UINT32)]

    class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
        _fields_ = [("Numerator", UINT32), ("Denominator", UINT32)]

    class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
        _fields_ = [("adapterId", LUID), ("id", UINT32), ("modeInfoIdx", UINT32),
                    ("outputTechnology", UINT32), ("rotation", UINT32),
                    ("scaling", UINT32), ("refreshRate", DISPLAYCONFIG_RATIONAL),
                    ("scanLineOrdering", UINT32), ("targetAvailable", wintypes.BOOL),
                    ("statusFlags", UINT32)]

    class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
        _fields_ = [("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
                    ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO), ("flags", UINT32)]

    class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
        # The mode union is opaque to us; we only need the array sized correctly
        # so QueryDisplayConfig accepts the buffer.
        _fields_ = [("infoType", UINT32), ("id", UINT32), ("adapterId", LUID),
                    ("data", ctypes.c_ubyte * 48)]

    class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
        _fields_ = [("type", UINT32), ("size", UINT32),
                    ("adapterId", LUID), ("id", UINT32)]

    class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
        _fields_ = [("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
                    ("viewGdiDeviceName", wintypes.WCHAR * 32)]

    class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
        _fields_ = [("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
                    ("value", UINT32),          # bitfield (see masks below)
                    ("colorEncoding", UINT32),
                    ("bitsPerColorChannel", UINT32)]

    QDC_ONLY_ACTIVE_PATHS = 0x00000002
    DEVICE_INFO_GET_SOURCE_NAME = 1
    DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
    ERROR_SUCCESS = 0
    ADVANCED_COLOR_ENABLED = 0x2   # value bit 1

    GetDisplayConfigBufferSizes = user32.GetDisplayConfigBufferSizes
    GetDisplayConfigBufferSizes.argtypes = [UINT32, ctypes.POINTER(UINT32), ctypes.POINTER(UINT32)]
    GetDisplayConfigBufferSizes.restype = wintypes.LONG
    QueryDisplayConfig = user32.QueryDisplayConfig
    DisplayConfigGetDeviceInfo = user32.DisplayConfigGetDeviceInfo
    DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]
    DisplayConfigGetDeviceInfo.restype = wintypes.LONG

    num_paths = UINT32()
    num_modes = UINT32()
    if GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS,
                                   ctypes.byref(num_paths), ctypes.byref(num_modes)) != ERROR_SUCCESS:
        return {}

    paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
    modes = (DISPLAYCONFIG_MODE_INFO * num_modes.value)()
    QueryDisplayConfig.argtypes = [
        UINT32, ctypes.POINTER(UINT32), ctypes.POINTER(DISPLAYCONFIG_PATH_INFO),
        ctypes.POINTER(UINT32), ctypes.POINTER(DISPLAYCONFIG_MODE_INFO), ctypes.c_void_p,
    ]
    QueryDisplayConfig.restype = wintypes.LONG
    if QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_paths), paths,
                          ctypes.byref(num_modes), modes, None) != ERROR_SUCCESS:
        return {}

    result: Dict[str, bool] = {}
    for i in range(num_paths.value):
        path = paths[i]

        # GDI name for this path's source.
        src = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
        src.header.type = DEVICE_INFO_GET_SOURCE_NAME
        src.header.size = ctypes.sizeof(DISPLAYCONFIG_SOURCE_DEVICE_NAME)
        src.header.adapterId = path.sourceInfo.adapterId
        src.header.id = path.sourceInfo.id
        if DisplayConfigGetDeviceInfo(ctypes.cast(
                ctypes.byref(src), ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER))) != ERROR_SUCCESS:
            continue
        gdi_name = str(src.viewGdiDeviceName)
        if not gdi_name:
            continue

        # Advanced-color (HDR) state for this path's target.
        adv = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        adv.header.type = DEVICE_INFO_GET_ADVANCED_COLOR_INFO
        adv.header.size = ctypes.sizeof(DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO)
        adv.header.adapterId = path.targetInfo.adapterId
        adv.header.id = path.targetInfo.id
        enabled = False
        if DisplayConfigGetDeviceInfo(ctypes.cast(
                ctypes.byref(adv), ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER))) == ERROR_SUCCESS:
            enabled = bool(adv.value & ADVANCED_COLOR_ENABLED)
        result[gdi_name] = enabled

    return result


def monitor_hdr_states() -> Dict[int, bool]:
    """Return ``{monitor_index: hdr_enabled}`` for all displays.

    Indices match ``capture.monitor_index`` (``EnumDisplayMonitors`` order).
    Returns an empty dict off-Windows or on any failure (callers treat a missing
    entry as SDR).
    """
    if sys.platform != "win32":
        return {}
    try:
        gdi_by_index = _gdi_names_by_index()
        hdr_by_name = _hdr_by_gdi_name()
    except Exception as exc:  # pragma: no cover - platform edge cases
        logger.debug("[HDR] state query failed: %s", exc)
        return {}
    return {i: bool(hdr_by_name.get(name, False)) for i, name in enumerate(gdi_by_index)}


class HdrDetector:
    """Caches per-monitor HDR state; refresh on display-change events.

    The DISPLAYCONFIG query is cheap but not free, so the pipeline keeps one
    detector and calls :meth:`refresh` only when displays change (the platform
    monitor already emits those events) rather than every frame.
    """

    def __init__(self) -> None:
        self._states: Dict[int, bool] = {}
        self.refresh()

    def refresh(self) -> Dict[int, bool]:
        """Re-query HDR state for all monitors and cache it.

        Logs only when the state actually changes so it can be called on a poll
        without spamming the log.
        """
        new_states = monitor_hdr_states()
        if new_states != self._states:
            on = [i for i, v in new_states.items() if v]
            logger.info("[HDR] Display HDR state: %s (HDR-on: %s)", new_states, on or "none")
        self._states = new_states
        return self._states

    def is_hdr(self, monitor_index: int) -> bool:
        """True when *monitor_index* currently has HDR/advanced color enabled."""
        return bool(self._states.get(monitor_index, False))
