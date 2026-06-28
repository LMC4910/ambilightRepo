"""Tests for the opt-in hook capture backend (DX11 game capture via a native
helper over shared memory).

Two layers:
  * Pure-Python protocol round-trip + wiring tests — no native binary needed.
  * A live integration test that drives the real ``capture_host.exe`` fake-frame
    generator; skipped automatically when the binary has not been built.
"""

import os
import struct
import sys
import time

import numpy as np
import pytest

import ambilight.hook_capture as hc
from ambilight.capture import ScreenCaptureManager
from ambilight.hook_capture import (
    CaptureHostProcess,
    HookCaptureBackend,
    SharedFrameBuffer,
    _downscale,
)


# ---------------------------------------------------------------------------
# Test helper: a Python writer that mimics native/capture_host/shm_writer.cpp.
# Validates that the Python reader's offsets/format match the documented
# protocol in native/shared_memory/shm_protocol.h.
# ---------------------------------------------------------------------------

def _write_slot(buf: SharedFrameBuffer, frame: np.ndarray, frame_id: int,
                timestamp_us: int = 0) -> None:
    h, w = frame.shape[:2]
    byte_size = w * h * hc.CHANNELS
    idx = frame_id % buf.slot_count
    slot_off = hc.CONTROL_BLOCK_SIZE + idx * buf.slot_stride
    mv = buf._buf

    seq = struct.unpack_from("<I", mv, slot_off)[0]
    struct.pack_into("<I", mv, slot_off, seq + 1)        # even -> odd (writing)

    struct.pack_into("<I", mv, slot_off + 4, w)          # width
    struct.pack_into("<I", mv, slot_off + 8, h)          # height
    struct.pack_into("<I", mv, slot_off + 12, hc.SHM_FORMAT_BGR)  # format
    struct.pack_into("<I", mv, slot_off + 16, byte_size)         # byte_size
    struct.pack_into("<Q", mv, slot_off + 24, frame_id)         # frame_id
    struct.pack_into("<Q", mv, slot_off + 32, timestamp_us)     # timestamp_us

    pix_off = slot_off + hc.SLOT_HEADER_SIZE
    mv[pix_off:pix_off + byte_size] = frame.tobytes()

    struct.pack_into("<I", mv, slot_off, seq + 2)        # odd -> even (stable)
    struct.pack_into("<q", mv, hc._LATEST_INDEX_OFF, idx)  # publish newest


def _distinct_bgr(h: int, w: int) -> np.ndarray:
    """A frame with a known B/G/R order and varied corners, so any channel-swap,
    stride, or reshape bug is caught."""
    f = np.empty((h, w, 3), np.uint8)
    f[..., 0] = 10   # B
    f[..., 1] = 20   # G
    f[..., 2] = 30   # R
    f[0, 0] = (1, 2, 3)
    f[h - 1, w - 1] = (40, 50, 60)
    return f


# ---------------------------------------------------------------------------
# Protocol round-trip
# ---------------------------------------------------------------------------

def test_read_latest_none_before_any_frame():
    buf = SharedFrameBuffer(8, 4)
    try:
        assert buf.read_latest() is None
    finally:
        buf.close()


def test_protocol_roundtrip_preserves_bgr_and_id():
    buf = SharedFrameBuffer(8, 4)
    try:
        frame = _distinct_bgr(4, 8)
        _write_slot(buf, frame, frame_id=0)

        got = buf.read_latest()
        assert got is not None
        fid, arr = got
        assert fid == 0
        assert arr.shape == (4, 8, 3)
        assert arr.dtype == np.uint8
        assert arr[0, 0].tolist() == [1, 2, 3]      # BGR order intact
        np.testing.assert_array_equal(arr, frame)
    finally:
        buf.close()


def test_newest_frame_wins_across_ring_slots():
    buf = SharedFrameBuffer(8, 4)
    try:
        # Write more frames than there are slots; the reader must return the last.
        last = None
        for fid in range(buf.slot_count + 2):
            last = (_distinct_bgr(4, 8) + fid).astype(np.uint8)
            _write_slot(buf, last, frame_id=fid)
        got = buf.read_latest()
        assert got is not None
        fid, arr = got
        assert fid == buf.slot_count + 1
        np.testing.assert_array_equal(arr, last)
    finally:
        buf.close()


def test_returned_frame_is_decoupled_from_shared_memory():
    buf = SharedFrameBuffer(8, 4)
    try:
        _write_slot(buf, _distinct_bgr(4, 8), frame_id=0)
        _, arr = buf.read_latest()
        # Overwriting the slot must not mutate the already-returned array.
        _write_slot(buf, np.full((4, 8, 3), 200, np.uint8), frame_id=0)
        assert arr[0, 0].tolist() == [1, 2, 3]
    finally:
        buf.close()


def test_control_block_geometry_is_aligned():
    buf = SharedFrameBuffer(1920, 1080)
    try:
        assert buf.slot_stride % 64 == 0
        assert buf.slot_stride >= hc.SLOT_HEADER_SIZE + 1920 * 1080 * 3
    finally:
        buf.close()


# ---------------------------------------------------------------------------
# Helpers + wiring
# ---------------------------------------------------------------------------

def test_downscale_preserves_channel_order_and_passthrough():
    f = np.empty((10, 10, 3), np.uint8)
    f[..., 0], f[..., 1], f[..., 2] = 10, 20, 30
    out = _downscale(f, (5, 5))
    assert out.shape == (5, 5, 3)
    assert out[0, 0].tolist() == [10, 20, 30]   # uniform image, BGR order kept
    assert _downscale(f, None) is f             # no target -> unchanged
    assert _downscale(f, (0, 0)) is f           # degenerate target -> unchanged


def test_resolve_exe_returns_path_or_none():
    p = CaptureHostProcess.resolve_exe()
    assert p is None or os.path.isfile(p)


def test_hook_backend_absent_from_default_chain():
    m = ScreenCaptureManager(preferred_method="wgc")
    names = [b.name for b in m._candidates]
    assert names == ["wgc", "dxgi", "mss"]
    assert "hook" not in names


def test_hook_backend_first_when_selected():
    m = ScreenCaptureManager(preferred_method="hook")
    names = [b.name for b in m._candidates]
    assert names == ["hook", "wgc", "dxgi", "mss"]


def test_unknown_method_falls_back_to_full_chain():
    m = ScreenCaptureManager(preferred_method="bogus")
    assert [b.name for b in m._candidates] == ["wgc", "dxgi", "mss"]


def test_open_returns_false_when_exe_missing(monkeypatch):
    monkeypatch.setattr(CaptureHostProcess, "resolve_exe", staticmethod(lambda: None))
    assert HookCaptureBackend().open({"index": 0}) is False


def test_backend_defaults_mode_hook_and_target_auto():
    be = HookCaptureBackend()
    assert be._mode == "hook"
    assert be._hook_target == "auto"   # empty hook_target -> auto-detect


def test_backend_accepts_fake_mode_and_custom_target():
    be = HookCaptureBackend(mode="fake", hook_target="Witcher3.exe")
    assert be._mode == "fake"
    assert be._hook_target == "Witcher3.exe"


def test_hook_target_threaded_from_manager():
    m = ScreenCaptureManager(preferred_method="hook", hook_target="game.exe")
    hook = next(b for b in m._candidates if b.name == "hook")
    assert hook._hook_target == "game.exe"


# ---------------------------------------------------------------------------
# Live integration — drives the real capture_host.exe fake frame generator.
# ---------------------------------------------------------------------------

_HOST_EXE = CaptureHostProcess.resolve_exe()


@pytest.mark.skipif(
    _HOST_EXE is None or sys.platform != "win32",
    reason="capture_host.exe not built (run cmake in native/)",
)
def test_live_host_delivers_animated_frames():
    be = HookCaptureBackend(mode="fake")  # transport test: drive the host's fake source
    assert be.open({"index": 0, "width": 320, "height": 180},
                   target_size=(80, 45), fps_target=30)
    try:
        frames = []
        for _ in range(12):
            f = be.grab()
            if f is not None:
                frames.append(f)
            time.sleep(0.04)
        assert frames, "no frames received from live host"
        assert frames[0].shape == (45, 80, 3)
        assert frames[0].dtype == np.uint8
        assert any(not np.array_equal(frames[0], g) for g in frames[1:]), \
            "frames did not animate — transport stalled"
    finally:
        be.close()
