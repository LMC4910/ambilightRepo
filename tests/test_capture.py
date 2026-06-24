"""Tests for capture backend selection + WGC fallback (FR-CAP-05, FR-CAP-09).

The real WGC/DXGI/MSS grabs need a display, so these cover the deterministic
logic: BGRA→BGR conversion, graceful WGC fallback, and manager promotion.
"""

import builtins
import logging
import sys
import types

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

    def open(self, monitor_index, target_size=None, fps_target=30):
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


class _ControllableBackend(CaptureBackend):
    """Fake backend whose open()/grab() behaviour can be flipped mid-test.

    Models a backend that can stall (``deliver = False`` → grab returns None, the
    transient lock/sleep symptom), die permanently (``can_open = False`` so a
    re-probe can't reopen it), or come back to life — and records open/close
    counts so recovery can be asserted.
    """

    def __init__(self, name="mss", can_open=True):
        self.name = name
        self.can_open = can_open
        self.deliver = True
        self.opened = 0
        self.closed = 0

    def open(self, monitor_index, target_size=None, fps_target=30):
        self.opened += 1
        return self.can_open

    def grab(self):
        return np.zeros((2, 2, 3), np.uint8) if self.deliver else None

    def close(self):
        self.closed += 1


def _fast(mgr):
    """Strip the rate-limit sleep and recovery cooldown so the failover state
    machine can be exercised synchronously without wall-clock waits."""
    mgr._frame_interval = 0.0
    mgr._COOLDOWN_S = 0.0
    return mgr


def test_mss_grab_reopens_dead_session():
    """MSSBackend rebuilds its session after a failure tore down the DC.

    Regression for the storm: a transient BitBlt failure used to leave the dead
    handle in place so every later grab failed forever. close() must null both
    the session and the monitor so the next grab re-runs _ensure_session."""
    from ambilight.capture import MSSBackend

    b = MSSBackend()
    b._sct = object()          # pretend a session exists
    b._monitor = {"left": 0}
    b.close()
    assert b._sct is None       # session released
    assert b._monitor is None   # monitor cleared too → lazy reopen arms


def test_mss_grab_failure_logs_once_not_per_frame(caplog):
    """A locked screen makes BitBlt raise on every grab; the warning must be
    latched to one line per outage, not ~fps lines/second (the original flood)."""
    from ambilight.capture import MSSBackend

    class _Boom:
        def grab(self, _monitor):
            raise OSError("BitBlt: The I/O operation has been aborted")

        def close(self):
            pass

    b = MSSBackend()
    # Force every (re)open to install a session that always fails on grab.
    b._ensure_session = lambda: (
        setattr(b, "_sct", _Boom()),
        setattr(b, "_monitor", {"left": 0, "top": 0, "width": 2, "height": 2}),
        True,
    )[-1]

    with caplog.at_level(logging.WARNING, logger="ambilight.capture"):
        for _ in range(25):
            assert b.grab() is None
    warnings = [r for r in caplog.records if "Frame grab failed" in r.getMessage()]
    assert len(warnings) == 1, f"MSS warning logged {len(warnings)}x (expected 1)"


def test_manager_recovers_active_backend_after_transient_stall():
    mgr = _fast(ScreenCaptureManager(preferred_method="mss", monitor_index=0))
    b = _ControllableBackend("mss")
    mgr._candidates = [b]
    mgr.start()
    assert mgr._active is b
    assert mgr.is_healthy

    # Transient stall (screen locked): grab returns None for a sustained run.
    b.deliver = False
    for _ in range(mgr._FAIL_THRESHOLD + 2):
        assert mgr.grab() is None
    assert b.closed >= 1     # manager closed the stalled session
    assert b.opened >= 2     # ...and re-probed the backend

    # Screen comes back: the backend delivers again and capture self-resumes
    # without the user touching anything.
    b.deliver = True
    frame = None
    for _ in range(mgr._FAIL_THRESHOLD + 2):
        frame = mgr.grab()
        if frame is not None:
            break
    assert frame is not None
    assert mgr.is_healthy
    assert mgr.active_backend == "mss"


def test_manager_exhaustion_logs_once_and_never_emits_question_mark(caplog):
    """The whole point of the fix: once exhausted, the manager must not spam.

    Previously every frame re-tripped the switch, logging 'Backend ? failed 10
    times' + 'All backends exhausted' ~2x/second (a 7.5 MB log). Now it logs the
    exhausted state once and backs off."""
    mgr = _fast(ScreenCaptureManager(preferred_method="mss", monitor_index=0))
    b = _ControllableBackend("mss")
    mgr._candidates = [b]
    mgr.start()

    b.deliver = False
    b.can_open = False          # can't be reopened → truly exhausted
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ambilight.capture"):
        for _ in range(300):
            assert mgr.grab() is None

    msgs = [r.getMessage() for r in caplog.records]
    exhausted = [m for m in msgs if "All backends exhausted" in m]
    assert len(exhausted) == 1, f"exhausted logged {len(exhausted)}x (expected 1)"
    assert not any("'?'" in m for m in msgs), "the '?' backend spam must be gone"
    assert not mgr.is_healthy


def test_manager_fails_over_to_second_backend_midrun():
    mgr = _fast(ScreenCaptureManager(preferred_method="wgc", monitor_index=0))
    primary = _ControllableBackend("wgc")
    secondary = _ControllableBackend("mss")
    mgr._candidates = [primary, secondary]
    mgr.start()
    assert mgr._active is primary

    # Primary dies for good; the manager should promote the healthy secondary.
    primary.deliver = False
    primary.can_open = False
    frame = None
    for _ in range(mgr._FAIL_THRESHOLD + 2):
        frame = mgr.grab()
    assert mgr._active is secondary
    assert frame is not None
    assert mgr.active_backend == "mss"


def test_manager_recovery_skips_backend_that_opens_but_delivers_nothing():
    """A higher-priority backend that re-opens but yields no frames (e.g. a locked
    screen) must not keep winning the re-probe and starving a working fallback —
    recovery requires a delivered frame, not just a successful open()."""
    mgr = _fast(ScreenCaptureManager(preferred_method="wgc", monitor_index=0))
    primary = _ControllableBackend("wgc")
    primary.deliver = False        # opens fine forever, but never yields a frame
    secondary = _ControllableBackend("mss")
    mgr._candidates = [primary, secondary]
    mgr.start()
    assert mgr._active is primary  # start() doesn't require a frame, lands on wgc

    frame = None
    for _ in range(mgr._FAIL_THRESHOLD + 2):
        frame = mgr.grab()
    # Recovery falls past the open-but-empty primary to the delivering secondary.
    assert mgr._active is secondary
    assert frame is not None
    assert mgr.active_backend == "mss"


def test_manager_recovery_respects_cooldown(monkeypatch):
    """With a real (nonzero) cooldown and a frozen clock, recovery must back off:
    no further open()/close() churn until the cooldown actually elapses. Guards
    the `now >= _next_retry_at` gate that the _fast() tests bypass."""
    clock = {"now": 100.0}
    monkeypatch.setattr("ambilight.capture.time.monotonic", lambda: clock["now"])

    mgr = ScreenCaptureManager(preferred_method="mss", monitor_index=0)
    mgr._frame_interval = 0.0      # no rate-limit sleep; keep the real cooldown
    mgr._COOLDOWN_S = 5.0
    b = _ControllableBackend("mss")
    mgr._candidates = [b]
    mgr.start()

    # Stall, then drive past the threshold to trigger the first recovery attempt.
    b.deliver = False
    for _ in range(mgr._FAIL_THRESHOLD):
        assert mgr.grab() is None
    opened_after_first = b.opened
    closed_after_first = b.closed
    assert opened_after_first >= 2  # start + one recovery probe

    # Clock frozen inside the cooldown window: no further re-probe churn.
    for _ in range(20):
        assert mgr.grab() is None
    assert b.opened == opened_after_first
    assert b.closed == closed_after_first

    # Advance past the cooldown → exactly one more recovery probe fires.
    clock["now"] += mgr._COOLDOWN_S
    assert mgr.grab() is None
    assert b.opened > opened_after_first


# --- identity-based target resolution -------------------------------------

def test_as_target_normalizes_int_and_dict():
    from ambilight.capture import _as_target
    assert _as_target(2) == {"index": 2}
    t = _as_target({"index": "3", "gdi_name": r"\\.\DISPLAY3"})
    assert t["index"] == 3 and t["gdi_name"] == r"\\.\DISPLAY3"
    assert _as_target("nope") == {"index": 0}      # non-numeric → 0


def test_match_output_by_gdi_then_position():
    from ambilight.capture import _match_output
    # Mirrors a real hybrid-GPU layout: outputs split across two adapters.
    outs = [
        {"device_idx": 0, "output_idx": 0, "gdi_name": r"\\.\DISPLAY5", "left": 0, "top": 0, "width": 1920, "height": 1080},
        {"device_idx": 0, "output_idx": 1, "gdi_name": r"\\.\DISPLAY4", "left": 1920, "top": 0, "width": 1080, "height": 1920},
        {"device_idx": 1, "output_idx": 0, "gdi_name": r"\\.\DISPLAY1", "left": 3000, "top": 0, "width": 1920, "height": 1080},
    ]
    # gdi_name wins, and addresses the right adapter (device 1) — not output_idx 2.
    assert _match_output(outs, {"gdi_name": r"\\.\DISPLAY1"}) == (1, 0)
    # same-resolution monitors are separated by position, never resolution.
    assert _match_output(outs, {"left": 1920, "top": 0}) == (0, 1)
    # not exposed by any DXGI output → unreachable.
    assert _match_output(outs, {"gdi_name": r"\\.\DISPLAY9", "left": 9, "top": 9}) is None


def _fake_mss(monkeypatch, virtual, *real):
    class _Sct:
        monitors = [virtual, *real]

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "mss", types.SimpleNamespace(mss=lambda: _Sct()))


def test_mss_open_matches_by_position_not_index(monkeypatch):
    """Same-resolution monitors: MSS must point at the target's position even when
    the bare index would pick a different one (e.g. mss order differs)."""
    from ambilight.capture import MSSBackend
    mon_a = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    mon_b = {"left": 1920, "top": 0, "width": 1920, "height": 1080}
    _fake_mss(monkeypatch, {"left": 0, "top": 0, "width": 3840, "height": 1080}, mon_a, mon_b)

    b = MSSBackend()
    # index 0 would select mon_a, but the target's position points at mon_b.
    assert b.open({"index": 0, "left": 1920, "top": 0}) is True
    assert b._monitor is mon_b


def test_mss_open_falls_back_to_index_without_position(monkeypatch):
    from ambilight.capture import MSSBackend
    mon_a = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    mon_b = {"left": 1920, "top": 0, "width": 1920, "height": 1080}
    _fake_mss(monkeypatch, {"left": 0, "top": 0, "width": 3840, "height": 1080}, mon_a, mon_b)

    b = MSSBackend()
    assert b.open({"index": 1}) is True   # no position hint → clamp by index
    assert b._monitor is mon_b


class _TargetAwareBackend(CaptureBackend):
    """Backend that can only capture a fixed set of monitor indices — models a
    DXGI adapter that simply doesn't expose an iGPU-driven panel."""

    def __init__(self, name, reachable):
        self.name = name
        self._reachable = set(reachable)

    def open(self, target, target_size=None, fps_target=30):
        from ambilight.capture import _as_target
        return _as_target(target).get("index") in self._reachable

    def grab(self):
        return np.zeros((2, 2, 3), np.uint8)

    def close(self):
        pass


def test_manager_promotes_backend_that_can_reach_target():
    """The user's scenario: a monitor unreachable by the preferred backend (DXGI)
    must fail over to one that can reach it (MSS)."""
    mgr = ScreenCaptureManager(preferred_method="dxgi", target={"index": 2, "gdi_name": r"\\.\DISPLAY3"})
    dxgi = _TargetAwareBackend("dxgi", reachable={0, 1})   # can't reach monitor 2
    mss = _TargetAwareBackend("mss", reachable={0, 1, 2})
    mgr._candidates = [dxgi, mss]
    mgr.start()
    assert mgr._active is mss
    assert mgr.active_backend == "mss"
