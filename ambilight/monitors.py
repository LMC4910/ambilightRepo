r"""
Monitor enumeration
====================
Lists connected displays with friendly names + resolution so the UI can show
"0 — Generic PnP Monitor (2560×1440, primary)" instead of a bare index — making
monitor selection no longer hit-and-trial.

The enumeration order (0-based) follows Win32 ``EnumDisplayMonitors``, which is
the same order the capture backends index by (dxcam ``output_idx``, mss
``monitors[1:]``, our ``capture.monitor_index``; WGC adds +1 internally).
Falls back to an mss-based list off Windows.

Beyond the bare index, each entry also carries **stable identifiers** so a
monitor can be re-found when the index doesn't line up across capture backends
(common on hybrid Intel-iGPU + discrete-GPU setups, where DXGI enumerates
outputs per adapter):

* ``id`` — EDID-derived (manufacturer + product + serial) suffixed with the
  physical-port UID, so even two *identical* panels stay distinct. Stable across
  reboots. Falls back to ``gdi_name`` then ``"pos:<left>,<top>"``.
* ``gdi_name`` — ``\\.\DISPLAYn``; unique within a session and equal to the
  ``DeviceName`` in DXGI's ``DXGI_OUTPUT_DESC``.
* ``left`` / ``top`` — virtual-desktop position; *always* unique (monitors tile
  the desktop, so no two share a top-left corner).

:func:`resolve_monitor` matches a stored identity back to the live monitor using
only these session-unique signals — never resolution, which two monitors can
share.
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


def _edid_stable_id(edid: bytes) -> Optional[str]:
    """Stable per-panel id from EDID: manufacturer + product code + serial.

    e.g. ``"GSM5B09-3F00C1A2"``. Two units of the same model differ by serial;
    identical serial-less panels (serial 0) are further disambiguated by the
    physical-port UID appended at the call site. Returns *None* if the blob is
    too short to parse.
    """
    if not edid or len(edid) < 16:
        return None
    try:
        m = (edid[8] << 8) | edid[9]
        mfg = "".join(chr(64 + ((m >> shift) & 0x1F)) for shift in (10, 5, 0))
        if not mfg.isalpha():
            return None
        product = (edid[11] << 8) | edid[10]  # little-endian
        serial = edid[12] | (edid[13] << 8) | (edid[14] << 16) | (edid[15] << 24)
        return f"{mfg}{product:04X}-{serial:08X}"
    except Exception:
        return None


def _port_uid(interface_id: str) -> Optional[str]:
    r"""Extract the physical-port token (e.g. ``"UID256"``) from a monitor
    device-interface path, so two identical panels on different ports get
    distinct ids. Returns *None* when the path has no instance segment.

    ``interface_id`` looks like
    ``\\?\DISPLAY#GSM5B09#5&abc123&0&UID256#{e6f07b5f-...}`` — the instance
    segment ``5&abc123&0&UID256`` encodes which GPU output drives the panel.
    """
    if not interface_id:
        return None
    parts = interface_id.split("#")
    if len(parts) < 3:
        return None
    instance = parts[2]
    for token in instance.split("&"):
        if token.upper().startswith("UID"):
            return token
    return instance or None


def _read_edid_info(interface_id: str) -> "tuple[Optional[str], Optional[str]]":
    r"""Map a monitor device-interface path to its registry EDID and parse it,
    returning ``(model_name, stable_id)``.

    ``interface_id`` looks like
    ``\\?\DISPLAY#GSM5B09#5&abc123&0&UID256#{e6f07b5f-...}``.
    """
    try:
        import winreg
    except Exception:
        return None, None
    parts = interface_id.split("#")
    if len(parts) < 3:
        return None, None
    hwid, instance = parts[1], parts[2]
    key_path = rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{hwid}\{instance}\Device Parameters"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            edid, _ = winreg.QueryValueEx(key, "EDID")
        blob = bytes(edid)
        return _edid_model_name(blob), _edid_stable_id(blob)
    except FileNotFoundError:
        return None, None
    except Exception as exc:  # pragma: no cover - registry edge cases
        logger.debug("[Monitors] EDID read failed for %s: %s", hwid, exc)
        return None, None


def _list_windows() -> List[Dict[str, Any]]:
    import ctypes
    from ctypes import wintypes

    # Use a PRIVATE user32 handle, not the process-wide ``ctypes.windll.user32``.
    # Setting ``.argtypes`` below mutates the cached function objects on whatever
    # WinDLL instance we use; the shared ``windll.user32`` is also used by dxcam
    # (``EnumDisplayDevicesW(0, …)`` with a NULL device), which then fails with
    # "argument 1: wrong type" once our LPCWSTR argtype is applied. A separate
    # instance keeps our argtype mutations local and leaves dxcam working.
    user32 = ctypes.WinDLL("user32")

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
            gdi_name = mi.szDevice  # \\.\DISPLAYn — unique within a session
            name = gdi_name
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            # Driver description ("Generic PnP Monitor") — last-resort label.
            if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd), 0) and dd.DeviceString:
                name = dd.DeviceString
            # Prefer the real model name + stable id from the monitor's EDID.
            # Re-query with the interface-name flag to get the device path the
            # registry uses (and the port UID baked into it).
            edid_id: Optional[str] = None
            port: Optional[str] = None
            dd2 = DISPLAY_DEVICEW()
            dd2.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd2), EDD_GET_DEVICE_INTERFACE_NAME) and dd2.DeviceID:
                model, edid_id = _read_edid_info(dd2.DeviceID)
                if model:
                    name = model
                port = _port_uid(dd2.DeviceID)
            left, top = mi.rcMonitor.left, mi.rcMonitor.top
            # Stable id: EDID identity + physical port (best), else the session
            # GDI name, else the always-unique virtual-desktop position.
            if edid_id:
                stable = f"{edid_id}-{port}" if port else edid_id
            elif gdi_name:
                stable = gdi_name
            else:
                stable = f"pos:{left},{top}"
            found.append({
                "id": stable,
                "name": name,
                "gdi_name": gdi_name,
                "width": mi.rcMonitor.right - left,
                "height": mi.rcMonitor.bottom - top,
                "left": left,
                "top": top,
                "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
            })
        return 1

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return [
        {
            "index": i, "id": m["id"], "name": m["name"], "gdi_name": m["gdi_name"],
            "width": m["width"], "height": m["height"],
            "left": m["left"], "top": m["top"], "primary": m["primary"],
        }
        for i, m in enumerate(found)
    ]


def _list_mss() -> List[Dict[str, Any]]:
    try:
        import mss
        with mss.mss() as sct:
            out: List[Dict[str, Any]] = []
            for i, m in enumerate(sct.monitors[1:]):
                left, top = m["left"], m["top"]
                out.append({
                    "index": i,
                    "id": f"pos:{left},{top}",  # position is always unique
                    "name": f"Display {i + 1}",
                    "gdi_name": "",
                    "width": m["width"], "height": m["height"],
                    "left": left, "top": top,
                    "primary": i == 0,
                })
            return out
    except Exception:
        return []


def list_monitors() -> List[Dict[str, Any]]:
    """Return per-display dicts for connected displays.

    Each entry is ``{index, id, name, gdi_name, width, height, left, top,
    primary}``. ``id``/``gdi_name``/``left``/``top`` are the stable identifiers
    :func:`resolve_monitor` matches on (see module docstring).
    """
    if sys.platform == "win32":
        try:
            mons = _list_windows()
            if mons:
                return mons
        except Exception as exc:  # pragma: no cover - platform edge cases
            logger.debug("[Monitors] Win32 enumeration failed: %s", exc)
    return _list_mss()


def _tiebreak(matches: List[Dict[str, Any]], stored: Dict[str, Any]) -> Dict[str, Any]:
    """Pick one monitor from several that share a stored ``id`` (identical
    serial-less panels). Prefers the stored position, then gdi_name, then index."""
    sleft, stop = stored.get("left"), stored.get("top")
    if sleft is not None and stop is not None:
        for m in matches:
            if m.get("left") == sleft and m.get("top") == stop:
                return m
    sgdi = (stored.get("gdi_name") or "").strip()
    if sgdi:
        for m in matches:
            if m.get("gdi_name") == sgdi:
                return m
    sindex = stored.get("index")
    if isinstance(sindex, int):
        for m in matches:
            if m.get("index") == sindex:
                return m
    return matches[0]


def resolve_monitor(
    stored: Dict[str, Any], monitors: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    r"""Find the live monitor matching a stored identity.

    Tries, in strict order — keying only on signals that are unique within a
    session, so two monitors sharing a resolution are never confused:

    1. exact ``id`` — if it matches >1 live monitor (identical serial-less
       panels), break the tie via :func:`_tiebreak`;
    2. ``gdi_name`` (``\\.\DISPLAYn``);
    3. ``(left, top)`` position;
    4. ``index`` (last resort).

    Returns the matched monitor dict (with its *current* index), or *None* when
    nothing matches and no usable index was supplied.
    """
    mons = monitors if monitors is not None else list_monitors()
    if not mons:
        return None

    sid = (stored.get("id") or "").strip()
    if sid:
        id_matches = [m for m in mons if m.get("id") == sid]
        if len(id_matches) == 1:
            return id_matches[0]
        if len(id_matches) > 1:
            return _tiebreak(id_matches, stored)

    sgdi = (stored.get("gdi_name") or "").strip()
    if sgdi:
        for m in mons:
            if m.get("gdi_name") and m.get("gdi_name") == sgdi:
                return m

    sleft, stop = stored.get("left"), stored.get("top")
    if sleft is not None and stop is not None:
        for m in mons:
            if m.get("left") == sleft and m.get("top") == stop:
                return m

    sindex = stored.get("index")
    if isinstance(sindex, int) and 0 <= sindex < len(mons):
        return mons[sindex]
    return None
