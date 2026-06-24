"""Tests for stable monitor identity + cross-backend resolution.

Covers the identifier derivation (EDID stable id, port UID) and
:func:`resolve_monitor` precedence — keying only on signals that are unique
within a session (id / gdi_name / position), never resolution, so two monitors
sharing a resolution (or two identical serial-less panels) are never confused.
"""

import sys
import types

import pytest

from ambilight.monitors import (
    _edid_stable_id, _port_uid, _list_mss, list_monitors, resolve_monitor,
)


# --- EDID stable id -------------------------------------------------------

def _edid_blob(mfg="ACR", product=0x10CA, serial=0x54606CFE):
    """Build a minimal 128-byte EDID with the identity fields populated."""
    b = bytearray(128)
    m = ((ord(mfg[0]) - 64) << 10) | ((ord(mfg[1]) - 64) << 5) | (ord(mfg[2]) - 64)
    b[8], b[9] = (m >> 8) & 0xFF, m & 0xFF              # manufacturer (big-endian)
    b[10], b[11] = product & 0xFF, (product >> 8) & 0xFF  # product (little-endian)
    for i, shift in enumerate((0, 8, 16, 24)):           # serial (little-endian)
        b[12 + i] = (serial >> shift) & 0xFF
    return bytes(b)


def test_edid_stable_id_combines_mfg_product_serial():
    assert _edid_stable_id(_edid_blob()) == "ACR10CA-54606CFE"


def test_edid_stable_id_serial_zero_still_parses():
    # Identical serial-less panels collide here; the port UID disambiguates them.
    assert _edid_stable_id(_edid_blob(serial=0)) == "ACR10CA-00000000"


def test_edid_stable_id_none_on_short_or_invalid():
    assert _edid_stable_id(b"\x00" * 8) is None      # too short
    assert _edid_stable_id(bytes(128)) is None       # mfg bytes 0 → non-alpha


def test_port_uid_extracts_uid_token():
    path = r"\\?\DISPLAY#GSM5B09#5&abc123&0&UID256#{e6f07b5f-0000}"
    assert _port_uid(path) == "UID256"


def test_port_uid_falls_back_to_instance_segment():
    assert _port_uid(r"\\?\DISPLAY#ACR0E24#4&deadbeef&0#{guid}") == "4&deadbeef&0"
    assert _port_uid("") is None


# --- resolve_monitor precedence ------------------------------------------
# mon0 and mon1 deliberately SHARE a resolution (1920x1080) with distinct ids,
# gdi names and positions, so the same-resolution case is exercised throughout.

MONS = [
    {"index": 0, "id": "ACR1-A-UID1", "gdi_name": r"\\.\DISPLAY1",
     "left": 0, "top": 0, "width": 1920, "height": 1080, "primary": True},
    {"index": 1, "id": "ACR1-B-UID2", "gdi_name": r"\\.\DISPLAY2",
     "left": 1920, "top": 0, "width": 1920, "height": 1080, "primary": False},
    {"index": 2, "id": "DEL2-C-UID3", "gdi_name": r"\\.\DISPLAY3",
     "left": 3840, "top": 0, "width": 2560, "height": 1440, "primary": False},
]


def test_resolve_prefers_exact_id():
    assert resolve_monitor({"id": "DEL2-C-UID3"}, MONS)["index"] == 2


def test_resolve_same_resolution_by_position_when_id_absent():
    # No id/gdi — two monitors share 1920x1080, so only position disambiguates.
    assert resolve_monitor({"left": 1920, "top": 0}, MONS)["index"] == 1
    assert resolve_monitor({"left": 0, "top": 0}, MONS)["index"] == 0


def test_resolve_falls_to_gdi_name_when_id_misses():
    assert resolve_monitor({"id": "stale", "gdi_name": r"\\.\DISPLAY2"}, MONS)["index"] == 1


def test_resolve_falls_to_position_when_id_and_gdi_miss():
    got = resolve_monitor({"id": "stale", "left": 1920, "top": 0}, MONS)
    assert got["index"] == 1


def test_resolve_index_is_last_resort():
    assert resolve_monitor({"index": 2}, MONS)["index"] == 2
    # A stale id with only an index hint falls all the way through to the index.
    assert resolve_monitor({"id": "nope", "index": 1}, MONS)["index"] == 1


def test_resolve_returns_none_when_nothing_matches():
    assert resolve_monitor({"id": "zzz"}, MONS) is None
    assert resolve_monitor({"id": "x"}, []) is None
    assert resolve_monitor({"index": 99}, MONS) is None  # out of range


# --- identical serial-less panels (same id) -------------------------------
# Two units of the same model with serial 0 share an id; the tiebreak must use
# position, then gdi_name, then index.

DUP = [
    {"index": 0, "id": "HKC0-00000000-UID1", "gdi_name": r"\\.\DISPLAY1",
     "left": 0, "top": 0, "width": 1920, "height": 1080, "primary": True},
    {"index": 1, "id": "HKC0-00000000-UID1", "gdi_name": r"\\.\DISPLAY2",
     "left": 1920, "top": 0, "width": 1920, "height": 1080, "primary": False},
]


def test_identical_panels_disambiguate_by_position():
    assert resolve_monitor({"id": "HKC0-00000000-UID1", "left": 1920, "top": 0}, DUP)["index"] == 1


def test_identical_panels_disambiguate_by_gdi_then_index():
    assert resolve_monitor({"id": "HKC0-00000000-UID1", "gdi_name": r"\\.\DISPLAY1"}, DUP)["index"] == 0
    assert resolve_monitor({"id": "HKC0-00000000-UID1", "index": 1}, DUP)["index"] == 1
    # No hints at all → first matching panel.
    assert resolve_monitor({"id": "HKC0-00000000-UID1"}, DUP)["index"] == 0


# --- mss fallback id format ----------------------------------------------

def test_list_mss_id_is_position(monkeypatch):
    class _Sct:
        monitors = [
            {"left": 0, "top": 0, "width": 9999, "height": 9999},   # virtual [0]
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},
        ]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "mss", types.SimpleNamespace(mss=lambda: _Sct()))
    out = _list_mss()
    assert [m["id"] for m in out] == ["pos:0,0", "pos:1920,0"]
    assert out[0]["primary"] is True and out[1]["primary"] is False


# --- shared-user32 isolation (regression) ---------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Win32 ctypes argtypes isolation")
def test_list_windows_does_not_pollute_shared_user32():
    """Enumeration must not mutate ``ctypes.windll.user32`` argtypes — dxcam
    reuses that handle and calls ``EnumDisplayDevicesW(0, …)`` with a NULL device;
    a leaked LPCWSTR argtype made dxcam raise "argument 1: wrong type" and killed
    the DXGI backend. We mutate a private ``WinDLL("user32")`` instead."""
    import ctypes

    shared = ctypes.windll.user32.EnumDisplayDevicesW
    before = getattr(shared, "argtypes", None)
    list_monitors()
    after = getattr(ctypes.windll.user32.EnumDisplayDevicesW, "argtypes", None)
    assert after == before  # shared handle untouched by our private WinDLL
