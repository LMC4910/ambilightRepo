"""Tests for full-screen-game capture health (G1).

An exclusive-fullscreen game on the MSS backend (and DRM-protected content on
any backend) yields a *valid all-black frame*, not ``None``, so it slips past
the pipeline's no-frames failover and the strip silently goes dark while health
reports green. These cover the two deterministic pieces of the fix: the
black-frame primitive and the sustained-black verdict (cause + threshold).
"""

import numpy as np

from ambilight.capture import is_black_frame, BLACK_LUMA_THRESHOLD
from ambilight.pipeline import _nosignal_verdict, _BLACK_NOSIGNAL_FRAMES


# --- is_black_frame -------------------------------------------------------

def test_is_black_frame_true_for_pure_black():
    assert is_black_frame(np.zeros((45, 80, 3), np.uint8)) is True


def test_is_black_frame_none_and_empty_are_not_black():
    # None is a capture *failure*, handled separately — not a black frame.
    assert is_black_frame(None) is False
    assert is_black_frame(np.empty((0, 0, 3), np.uint8)) is False


def test_is_black_frame_false_for_a_dim_but_real_scene():
    # A genuinely dark game scene sits above the tiny threshold and must NOT
    # be mistaken for no-signal.
    frame = np.full((45, 80, 3), 30, np.uint8)
    assert is_black_frame(frame) is False


def test_is_black_frame_threshold_boundary():
    at = np.full((10, 10, 3), int(BLACK_LUMA_THRESHOLD), np.uint8)
    above = np.full((10, 10, 3), int(BLACK_LUMA_THRESHOLD) + 5, np.uint8)
    assert is_black_frame(at) is True            # mean <= threshold
    assert is_black_frame(above) is False


# --- _nosignal_verdict ----------------------------------------------------

def test_brief_black_run_is_not_a_fault():
    ok, reason = _nosignal_verdict(_BLACK_NOSIGNAL_FRAMES - 1, "mss")
    assert ok is True and reason == "ok"


def test_sustained_black_on_mss_flags_black_cause():
    ok, reason = _nosignal_verdict(_BLACK_NOSIGNAL_FRAMES, "mss")
    assert ok is False and reason == "black"


def test_sustained_black_on_wgc_suspects_drm():
    # WGC/DXGI *can* see fullscreen games, so persistent black is most likely DRM.
    for backend in ("wgc", "dxgi"):
        ok, reason = _nosignal_verdict(_BLACK_NOSIGNAL_FRAMES + 10, backend)
        assert ok is False and reason == "drm_suspected"
