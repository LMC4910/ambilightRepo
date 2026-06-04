"""Tests for capture backend selection + WGC fallback (FR-CAP-05, FR-CAP-09).

The real WGC/DXGI/MSS grabs need a display, so these cover the deterministic
logic: BGRA→BGR conversion, graceful WGC fallback, and manager promotion.
"""

import builtins
import sys

import numpy as np

from ambilight.capture import (
    WGCBackend, CaptureBackend, ScreenCaptureManager, _bgra_to_bgr,
)


def test_bgra_to_bgr_drops_alpha_and_is_contiguous():
    bgra = np.dstack([
        np.full((4, 5), 10, np.uint8),   # B
        np.full((4, 5), 20, np.uint8),   # G
        np.full((4, 5), 30, np.uint8),   # R
        np.full((4, 5), 99, np.uint8),   # A (dropped)
    ])
    bgr = _bgra_to_bgr(bgra)
    assert bgr.shape == (4, 5, 3)
    assert bgr.dtype == np.uint8
    assert bgr.flags["C_CONTIGUOUS"]
    assert bgr[0, 0].tolist() == [10, 20, 30]


def test_wgc_store_and_grab_roundtrip():
    b = WGCBackend()
    b._available = True
    bgra = np.zeros((3, 3, 4), np.uint8)
    bgra[..., 2] = 200            # red channel
    b._store_frame(bgra)
    frame = b.grab()
    assert frame is not None and frame.shape == (3, 3, 3)
    assert int(frame[..., 2].mean()) == 200


def test_wgc_grab_none_until_available():
    b = WGCBackend()
    assert b.grab() is None       # not available, no frame yet


def test_wgc_open_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert WGCBackend().open(0) is False


def test_wgc_open_false_when_library_missing(monkeypatch):
    # Force a win32 environment but make the windows_capture import fail.
    monkeypatch.setattr(sys, "platform", "win32")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "windows_capture" or name.startswith("windows_capture."):
            raise ImportError("simulated missing windows-capture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert WGCBackend().open(0) is False     # graceful, no raise


class _FakeBackend(CaptureBackend):
    def __init__(self, name, can_open):
        self.name = name
        self._can_open = can_open
        self.closed = False

    def open(self, monitor_index):
        return self._can_open

    def grab(self):
        return np.zeros((2, 2, 3), np.uint8)

    def close(self):
        self.closed = True


def test_manager_falls_back_to_next_backend():
    mgr = ScreenCaptureManager(preferred_method="wgc", monitor_index=0)
    wgc = _FakeBackend("wgc", can_open=False)
    dxgi = _FakeBackend("dxgi", can_open=True)
    mgr._candidates = [wgc, dxgi]
    mgr.start()
    assert mgr._active is dxgi      # WGC unavailable → promotes DXGI


def test_manager_raises_when_all_unavailable():
    mgr = ScreenCaptureManager(preferred_method="wgc", monitor_index=0)
    mgr._candidates = [_FakeBackend("wgc", False), _FakeBackend("mss", False)]
    try:
        mgr.start()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError when no backend opens")
