"""
Monitor enumeration
====================
Lists connected displays with friendly names + resolution so the UI can show
"0 — Generic PnP Monitor (2560×1440, primary)" instead of a bare index — making
monitor selection no longer hit-and-trial.

The enumeration order (0-based) follows Win32 ``EnumDisplayMonitors``, which is
the same order the capture backends index by (dxcam ``output_idx``, mss
``monitors[1:]``, our ``capture.monitor_index``; WGC adds +1 internally).
Falls back to an mss-based list off Windows.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --- EDID parsing: recover the real monitor model name ---------------------
#
# ``EnumDisplayDevicesW`` only reports the driver description ("Generic PnP
# Monitor"). The actual product name (e.g. "LG ULTRAGEAR", "27GL850") lives in
# the monitor's EDID blob, which Windows caches in the registry under
# ``HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY\<hwid>\<instance>\Device Parameters\EDID``.

def _edid_model_name(edid: bytes) -> Optional[str]:
    """Extract the monitor model from a 128-byte EDID block, if present."""
    if not edid or len(edid) < 128:
        return None
    # Descriptor blocks live at offsets 54/72/90/108 (18 bytes each). A block
    # tagged 0xFC (bytes 0..2 == 0 and byte 3 == 0xFC) holds the monitor name.
    name = None
    for off in (54, 72, 90, 108):
        block = edid[off:off + 18]
        if len(block) == 18 and block[0] == 0 and block[1] == 0 and block[2] == 0 and block[3] == 0xFC:
            text = bytes(block[5:18]).split(b"\n")[0].split(b"\x00")[0]
            s = text.decode("ascii", "ignore").strip()
            if s:
                name = s
    if name:
        return name
    # Fallback: PNP manufacturer id (bytes 8-9) + product code (bytes 10-11).
    try:
        m = (edid[8] << 8) | edid[9]
        mfg = "".join(chr(64 + ((m >> shift) & 0x1F)) for shift in (10, 5, 0))
        product = edid[11] << 8 | edid[10]  # little-endian
        if mfg.isalpha():
            return f"{mfg} {product:04X}"
    except Exception:
        pass
    return None


def _read_edid_name(interface_id: str) -> Optional[str]:
    r"""Map a monitor device-interface path to its registry EDID and parse it.

    ``interface_id`` looks like
    ``\\?\DISPLAY#GSM5B09#5&abc123&0&UID256#{e6f07b5f-...}``.
    """
    try:
        import winreg
    except Exception:
        return None
    parts = interface_id.split("#")
    if len(parts) < 3:
        return None
    hwid, instance = parts[1], parts[2]
    key_path = rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{hwid}\{instance}\Device Parameters"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            edid, _ = winreg.QueryValueEx(key, "EDID")
        return _edid_model_name(bytes(edid))
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover - registry edge cases
        logger.debug("[Monitors] EDID read failed for %s: %s", hwid, exc)
        return None


def _list_windows() -> List[Dict[str, Any]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                    ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                    ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

    MONITORINFOF_PRIMARY = 0x1
    EDD_GET_DEVICE_INTERFACE_NAME = 0x1
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
    )
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    found: List[Dict[str, Any]] = []

    def _cb(hmon, _hdc, _lprc, _lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            name = mi.szDevice
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            # Driver description ("Generic PnP Monitor") — last-resort label.
            if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd), 0) and dd.DeviceString:
                name = dd.DeviceString
            # Prefer the real model name from the monitor's EDID. Re-query with
            # the interface-name flag to get the device path the registry uses.
            dd2 = DISPLAY_DEVICEW()
            dd2.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd2), EDD_GET_DEVICE_INTERFACE_NAME) and dd2.DeviceID:
                model = _read_edid_name(dd2.DeviceID)
                if model:
                    name = model
            found.append({
                "name": name,
                "width": mi.rcMonitor.right - mi.rcMonitor.left,
                "height": mi.rcMonitor.bottom - mi.rcMonitor.top,
                "left": mi.rcMonitor.left,
                "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
            })
        return 1

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return [
        {"index": i, "name": m["name"], "width": m["width"], "height": m["height"], "primary": m["primary"]}
        for i, m in enumerate(found)
    ]


def _list_mss() -> List[Dict[str, Any]]:
    try:
        import mss
        with mss.mss() as sct:
            return [
                {"index": i, "name": f"Display {i + 1}", "width": m["width"], "height": m["height"], "primary": i == 0}
                for i, m in enumerate(sct.monitors[1:])
            ]
    except Exception:
        return []


def list_monitors() -> List[Dict[str, Any]]:
    """Return ``[{index, name, width, height, primary}]`` for connected displays."""
    if sys.platform == "win32":
        try:
            mons = _list_windows()
            if mons:
                return mons
        except Exception as exc:  # pragma: no cover - platform edge cases
            logger.debug("[Monitors] Win32 enumeration failed: %s", exc)
    return _list_mss()
