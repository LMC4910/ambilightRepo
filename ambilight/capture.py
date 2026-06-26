"""
Screen Capture Module
=====================
Provides a unified :class:`ScreenCaptureManager` that selects the fastest
available capture backend at runtime and automatically falls back when a
backend fails mid-run.

Backend priority
----------------
1. **Windows Graphics Capture API** (``wgc``) — captures the DWM-composited
   output via the native ``windows-capture`` package, so it picks up
   hardware-accelerated video overlay/MPO planes that DXGI misses. Does NOT
   bypass hardware DRM (HDCP/PlayReady stays black). Requires Windows 10 1903+.
2. **DXGI Desktop Duplication** (``dxgi``) — very fast, GPU-native; misses some
   hardware-overlay video. Requires ``dxcam``.
3. **MSS** (``mss``) — pure-Python cross-platform fallback.  Higher CPU
   overhead but zero extra dependencies.

Every backend exposes a common :class:`CaptureBackend` interface with a
single ``grab() -> np.ndarray | None`` method that returns a BGR uint8
frame (H×W×3) or *None* when the backend has failed and a switch is needed.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# Mean-luminance (0-255) at or below which an analysis frame is considered
# "black". Deliberately tiny so only near-perfect black trips it — a genuine
# dark scene still sits well above this, while a stuck/no-signal capture
# (fullscreen game on the MSS backend, or DRM-protected content) reads ~0.
BLACK_LUMA_THRESHOLD: float = 6.0


def is_black_frame(frame: Optional[np.ndarray], threshold: float = BLACK_LUMA_THRESHOLD) -> bool:
    """Return True when *frame* is (near-)uniformly black.

    Used by the pipeline to distinguish a capture that is *delivering* frames
    but producing nothing visible — the silent "lights don't react to my game"
    symptom when an exclusive-fullscreen game lands on the MSS backend (which
    returns a valid all-black frame rather than ``None``) or when DRM-protected
    content is on screen. A ``None`` frame is a capture *failure*, not a black
    frame, so it returns False here (the manager handles failures separately).
    """
    if frame is None or frame.size == 0:
        return False
    return float(frame.mean()) <= threshold


# ---------------------------------------------------------------------------
# Monitor target resolution
# ---------------------------------------------------------------------------
#
# A capture *target* is a monitor identity bundle — not a bare index — so each
# backend can map it to its own addressing using session-unique signals
# (``gdi_name`` / position), never resolution. This is what fixes hybrid-GPU
# setups where a global index points at a different physical monitor (or none)
# under DXGI than under WGC/MSS.

def _as_target(monitor) -> dict:
    """Normalise a capture target into an identity dict.

    Accepts either a bare 0-based monitor index (legacy callers / tests) or a
    resolved monitor dict from :func:`ambilight.monitors.resolve_monitor` /
    ``list_monitors`` (``{index, id, gdi_name, left, top, width, height, …}``).
    Always returns a dict carrying at least ``index``.
    """
    if isinstance(monitor, dict):
        t = dict(monitor)
        try:
            t["index"] = int(t.get("index", 0))
        except (TypeError, ValueError):
            t["index"] = 0
        return t
    try:
        return {"index": int(monitor)}
    except (TypeError, ValueError):
        return {"index": 0}


def _dxgi_outputs(dxcam) -> "list[dict]":
    r"""Enumerate DXGI outputs in dxcam's (adapter, output) order.

    Returns ``[{device_idx, output_idx, gdi_name, left, top, width, height}]``.
    Reads dxcam's already-built output factory, so the indices line up exactly
    with ``dxcam.create(device_idx, output_idx)``. ``gdi_name`` (``\\.\DISPLAYn``)
    and position come straight from each output's ``DXGI_OUTPUT_DESC``. Raises if
    the factory/descriptors are unavailable, so the caller falls back to index
    addressing.
    """
    # Reuse the module-level singleton instance to avoid dxcam's "only 1
    # instance allowed" warning that calling DXFactory() again would emit.
    factory = getattr(dxcam, "__factory", None) or dxcam.DXFactory()
    outs: "list[dict]" = []
    for didx, outputs in enumerate(factory.outputs):
        for oidx, output in enumerate(outputs):
            coords = output.desc.DesktopCoordinates
            outs.append({
                "device_idx": didx,
                "output_idx": oidx,
                "gdi_name": output.devicename,
                "left": int(coords.left),
                "top": int(coords.top),
                "width": int(coords.right - coords.left),
                "height": int(coords.bottom - coords.top),
            })
    return outs


def _match_output(outputs: "list[dict]", target: dict) -> "Optional[tuple[int, int]]":
    """Pick the ``(device_idx, output_idx)`` whose DXGI output matches *target*
    by ``gdi_name`` first, then ``(left, top)`` — both unique within a session,
    so same-resolution monitors are never confused. Returns *None* when nothing
    matches (the monitor isn't reachable via DXGI)."""
    gdi = (target.get("gdi_name") or "").strip()
    if gdi:
        for o in outputs:
            if o.get("gdi_name") == gdi:
                return o["device_idx"], o["output_idx"]
    left, top = target.get("left"), target.get("top")
    if left is not None and top is not None:
        for o in outputs:
            if o.get("left") == left and o.get("top") == top:
                return o["device_idx"], o["output_idx"]
    return None


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------

class CaptureBackend(ABC):
    """Interface that all capture backends must implement."""

    name: str = "base"

    @abstractmethod
    def open(self, target, target_size=None, fps_target: int = 30) -> bool:
        """
        Initialise the backend for *target*.

        *target* is either a bare 0-based monitor index (legacy) or a resolved
        monitor dict (``{index, id, gdi_name, left, top, width, height, …}``)
        from :func:`ambilight.monitors.resolve_monitor`. Backends map it to their
        own internal addressing using session-unique signals (``gdi_name`` /
        position), never resolution; one that *cannot* reach the target returns
        *False* so the manager promotes the next backend.

        ``target_size`` is the optional ``(width, height)`` the backend may
        pre-downscale to (used by WGC); ``fps_target`` caps delivery rate.
        Returns *True* on success, *False* if the backend is unavailable.
        """

    @abstractmethod
    def grab(self) -> Optional[np.ndarray]:
        """
        Capture one frame.

        Returns
        -------
        numpy.ndarray or None
            BGR uint8 array (H×W×3), or *None* when the backend has failed.
        """

    @abstractmethod
    def close(self) -> None:
        """Release all resources."""


# ---------------------------------------------------------------------------
# Windows Graphics Capture backend
# ---------------------------------------------------------------------------

def _bgra_to_bgr(buffer: np.ndarray, target_size=None) -> np.ndarray:
    """Convert a WGC ``frame_buffer`` (H×W×4 BGRA) to a contiguous H×W×3 BGR array,
    optionally downscaling to ``target_size`` = ``(width, height)``.

    The library reuses its buffer between callbacks, so the result is copied to
    decouple it from the capture thread. Pillow's resize releases the GIL.
    """
    arr = np.asarray(buffer)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        arr = arr[:, :, :3]
    if target_size is not None:
        tw, th = target_size
        if tw and th and (arr.shape[1] != tw or arr.shape[0] != th):
            from PIL import Image
            arr = np.asarray(Image.fromarray(arr).resize((tw, th), Image.BILINEAR))
    return np.ascontiguousarray(arr)


class WGCBackend(CaptureBackend):
    """
    Windows Graphics Capture API backend (FR-CAP-05).

    Implemented with the native ``windows-capture`` package (``pip install
    windows-capture``), which runs the full WGC + Direct3D 11 + texture→numpy
    pipeline and delivers BGRA frames on its own capture thread. We adapt that
    push model to the manager's pull model by keeping the latest frame.

    WGC captures the DWM-composited output, so it picks up hardware-accelerated
    video **overlay/MPO planes** that DXGI Desktop Duplication misses (a common
    "black video" fix). It does **not** bypass hardware DRM — HDCP/PlayReady
    protected playback is excluded by Windows and remains black here too.

    Falls back gracefully (``open`` returns False) when not on Windows or when
    ``windows-capture`` is unavailable, so the manager promotes DXGI/MSS.

    Auto-restart on ``on_closed``
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    When a game enters exclusive-fullscreen mode, Windows terminates the WGC
    capture session and fires ``on_closed``.  The backend schedules a background
    restart thread that retries with progressive back-off.  As soon as the game
    drops exclusive mode (alt-tab, loading screen, etc.) the restart succeeds
    and the session self-heals — without waiting for the manager's recovery
    cooldown cycle.  ``close()`` (called by the manager) clears the stored
    session parameters, signalling the worker to stop.
    """

    name = "wgc"

    def __init__(self) -> None:
        self._control: Optional[object] = None
        self._available = False
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._target_size: Optional[tuple[int, int]] = None  # (width, height) to pre-downscale to
        # Session parameters stored so the auto-restart worker can reopen the
        # same monitor. Cleared by close() so the worker knows to stop.
        self._session_target: Optional[dict] = None
        self._session_target_size: Optional[tuple[int, int]] = None
        self._session_fps: int = 30
        # Daemon thread reference — only one restart attempt runs at a time.
        self._restart_thread: Optional[threading.Thread] = None

    def _store_frame(self, buffer: np.ndarray) -> None:
        """Callback sink (runs on the capture thread): downscale to the analysis
        size *here* and stash it. Downscaling in the callback (vs. copying the
        full ~25 MB frame and resizing in the pipeline) is what keeps screen-sync
        fast during high-FPS games — Pillow's resize releases the GIL, so the
        pipeline thread isn't starved."""
        bgr = _bgra_to_bgr(buffer, self._target_size)
        with self._lock:
            self._latest_frame = bgr

    def open(self, target, target_size=None, fps_target: int = 30) -> bool:
        try:
            import sys
            import time as _time
            if sys.platform != "win32":
                return False

            # Stop any existing session before starting a new one — prevents
            # resource leaks when open() is called on an already-running backend
            # (e.g. the manager's recovery runs while the auto-restart worker
            # also has an active session).
            if self._control is not None or self._available:
                self.close()

            # Lazy import — ImportError on non-Windows or if the package/native
            # extension is missing, which the manager handles by failing over.
            from windows_capture import WindowsCapture  # type: ignore[import-untyped]

            # WGC follows EnumDisplayMonitors order, the same order the resolved
            # target's index is in, so the index is the correct addressing here.
            t = _as_target(target)
            monitor_index = int(t.get("index", 0))
            self._target_size = target_size
            # Store session parameters for the auto-restart worker before
            # starting the capture thread.
            self._session_target = t
            self._session_target_size = target_size
            self._session_fps = fps_target
            # Cap delivery to the target FPS (ms) so a 144 FPS game doesn't flood
            # the callback. Without this the GIL is held copying frames at the
            # game's rate and the pipeline collapses to 1-2 FPS.
            min_interval_ms = max(1, int(round(1000.0 / max(fps_target, 1))))

            # windows-capture monitor_index is 1-based; our config is 0-based.
            capture = WindowsCapture(
                cursor_capture=False,
                draw_border=False,
                minimum_update_interval=min_interval_ms,
                monitor_index=monitor_index + 1,
            )

            @capture.event
            def on_frame_arrived(frame, capture_control):  # type: ignore[no-untyped-def]
                try:
                    self._store_frame(frame.frame_buffer)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("[WGC] frame handler error: %s", exc)

            @capture.event
            def on_closed():  # type: ignore[no-untyped-def]
                self._available = False
                # A game entering exclusive fullscreen terminates our WGC
                # session.  Schedule a background restart so we resume as soon
                # as the game drops exclusive mode — without waiting for the
                # manager's recovery cooldown.
                self._schedule_restart()

            self._control = capture.start_free_threaded()
            self._available = True
            # Wait briefly for the first frame so the manager doesn't treat the
            # async startup gap as a backend failure and fall over to DXGI/MSS.
            for _ in range(50):
                with self._lock:
                    if self._latest_frame is not None:
                        break
                _time.sleep(0.02)
            logger.info("[WGC] Capture session started for monitor %d (cap %d ms).", monitor_index, min_interval_ms)
            return True

        except Exception as exc:
            # info (not debug) so the *reason* WGC didn't load reaches the log —
            # a missing dependency (ImportError) vs. a runtime D3D/WinRT error are
            # diagnosed very differently, and otherwise we only see the downstream
            # "fell back to MSS" symptom. Only reached on Windows (non-Windows
            # returns False above before importing).
            logger.info("[WGC] Backend unavailable: %s: %s", type(exc).__name__, exc)
            return False

    def _schedule_restart(self) -> None:
        """Schedule a background restart of the WGC capture session.

        Invoked from the ``on_closed`` event handler, which fires when Windows
        terminates the session (typically when a game enters exclusive
        fullscreen).  Idempotent — if a restart thread is already running, a
        second call is a no-op; the existing worker keeps retrying.
        """
        if self._session_target is None:
            return  # close() was already called by the manager; don't restart
        if self._restart_thread is not None and self._restart_thread.is_alive():
            return  # restart already in progress
        t = threading.Thread(
            target=self._restart_worker,
            daemon=True,
            name="WGCAutoRestart",
        )
        self._restart_thread = t
        t.start()

    def _restart_worker(self) -> None:
        """Background worker: retry opening the WGC session after ``on_closed``.

        Waits progressively longer between attempts (up to 10 s) so a game
        holding exclusive control for a long time does not hammer the WGC API.
        Stops when:

        * The session comes back (``_available`` True *and* a frame delivered).
        * ``close()`` was called by the manager (``_session_target`` is None).
        * All retry attempts are exhausted (the manager's own recovery handles
          the fallback from this point).
        """
        import time as _time
        _time.sleep(1.0)  # brief grace period before the first attempt
        for attempt in range(15):  # up to ~2 minutes of retry time
            # Snapshot session params *before* calling close(), which clears them.
            target = self._session_target
            target_size = self._session_target_size
            fps = self._session_fps
            # Stop if the manager took over (cleared _session_target) or if a
            # previous attempt already restored the session.
            if target is None or self._available:
                return
            try:
                self.close()
                opened = self.open(target, target_size, fps)
                if opened:
                    with self._lock:
                        has_frame = self._latest_frame is not None
                    if has_frame:
                        logger.info("[WGC] Session auto-restarted (attempt %d).", attempt + 1)
                        return
                    logger.debug(
                        "[WGC] Auto-restart attempt %d: session opened, awaiting first frame.",
                        attempt + 1,
                    )
                else:
                    logger.debug(
                        "[WGC] Auto-restart attempt %d: open() failed.", attempt + 1,
                    )
            except Exception as exc:
                logger.debug("[WGC] Auto-restart attempt %d error: %s", attempt + 1, exc)
            # Progressive back-off, capped at 10 s.
            _time.sleep(min(float(attempt + 1), 10.0))
        logger.debug(
            "[WGC] Auto-restart exhausted after 15 attempts; manager recovery will continue.",
        )

    def grab(self) -> Optional[np.ndarray]:
        if not self._available:
            return None
        with self._lock:
            return self._latest_frame  # BGR uint8 (already downscaled), or None until first frame

    def close(self) -> None:
        # Clear session params first so a concurrent _restart_worker exits cleanly.
        self._session_target = None
        try:
            if self._control is not None:
                self._control.stop()
        except Exception:
            pass
        self._control = None
        self._available = False
        with self._lock:
            self._latest_frame = None


# ---------------------------------------------------------------------------
# DXGI Desktop Duplication backend
# ---------------------------------------------------------------------------

class DXGIBackend(CaptureBackend):
    """
    DXGI Desktop Duplication via **dxcam** (``pip install dxcam``).

    dxcam wraps the low-level DXGI Desktop Duplication API and exposes a
    simple ``grab()`` call.  It is faster than MSS and works with most
    content except DRM-protected video.
    """

    name = "dxgi"

    # Adapters to probe when the default (device 0) duplicates black. Covers
    # the common 2-GPU Optimus laptop plus a little headroom for odd setups.
    _MAX_DEVICES = 4

    def __init__(self) -> None:
        self._camera: Optional[object] = None

    def open(self, target, target_size=None, fps_target: int = 30) -> bool:
        try:
            import sys
            if sys.platform != "win32":
                return False

            import dxcam  # type: ignore[import-untyped]
            t = _as_target(target)
            camera = self._open_on_best_device(dxcam, t, fps_target)
            if camera is None:
                logger.info(
                    "[DXGI] dxcam imported but no adapter could duplicate monitor "
                    "(id=%s, index=%s); falling back.", t.get("id"), t.get("index"),
                )
                return False
            self._camera = camera
            logger.info(
                "[DXGI] dxcam capture started for monitor index %s (id=%s).",
                t.get("index"), t.get("id"),
            )
            return True
        except Exception as exc:
            # info (not debug) so a missing/under-bundled dxcam or comtypes shows
            # up in the log instead of silently degrading to MSS. Only reached on
            # Windows (non-Windows returns False above before importing).
            logger.info("[DXGI] Backend unavailable: %s: %s", type(exc).__name__, exc)
            return False

    def _open_on_best_device(self, dxcam, target: dict, fps_target: int):
        """Return a started dxcam camera for *target*, or ``None`` if DXGI cannot
        reach that monitor.

        Resolution path:

        1. **Identity match (multi-adapter correct).** Enumerate the DXGI outputs
           and pick the ``(device_idx, output_idx)`` whose ``gdi_name``/position
           equals the target's. This addresses the right adapter directly — the
           fix for hybrid-GPU setups where a global index points DXGI at the wrong
           output (or off the end of an adapter). If the monitor exists to Windows
           but *no* DXGI output exposes it (e.g. an iGPU-driven panel absent from
           this dGPU), return ``None`` so the manager fails over.
        2. **Fallback (single-GPU / enumeration unavailable).** Probe adapters
           0..N for the target's index — the original Optimus-black behaviour.
        """
        pairs = None  # explicit [(device_idx, output_idx)] once resolved by identity
        has_identity = bool((target.get("gdi_name") or "").strip()) or target.get("left") is not None
        try:
            outs = _dxgi_outputs(dxcam)
            if outs:
                matched = _match_output(outs, target)
                if matched is not None:
                    pairs = [matched]
                elif has_identity:
                    # Known monitor, but no DXGI output exposes it — unreachable.
                    logger.info(
                        "[DXGI] monitor (id=%s) is not exposed by any DXGI output; "
                        "failing over to another backend.", target.get("id"),
                    )
                    return None
        except Exception as exc:
            logger.debug("[DXGI] output enumeration failed (%s); using index probe.", exc)

        if pairs is None:
            output_idx = int(target.get("index", 0))
            pairs = [(dev, output_idx) for dev in range(self._MAX_DEVICES)]

        fallback = None  # first frame-delivering (but black) camera, as last resort
        for dev, out in pairs:
            try:
                cam = dxcam.create(device_idx=dev, output_idx=out, output_color="BGR")
            except Exception:
                continue  # this (device, output) pair doesn't exist
            if cam is None:
                continue
            try:
                cam.start(target_fps=max(int(fps_target), 30), video_mode=True)
            except Exception:
                self._safe_stop(cam)
                continue

            frame = None
            for _ in range(30):  # ~0.6s warm-up budget for the first frame
                frame = cam.get_latest_frame()
                if frame is not None:
                    break
                time.sleep(0.02)

            if frame is not None and float(frame.mean()) > BLACK_LUMA_THRESHOLD:
                if dev != 0:
                    logger.info(
                        "[DXGI] Capturing from GPU adapter %d, output %d.", dev, out,
                    )
                if fallback is not None:
                    self._safe_stop(fallback)
                return cam

            # Black or no frame: keep the first usable camera as a last resort,
            # release any extras so we don't leak duplication sessions.
            if fallback is None and frame is not None:
                fallback = cam
            else:
                self._safe_stop(cam)

        return fallback

    @staticmethod
    def _safe_stop(camera) -> None:
        try:
            camera.stop()
        except Exception:
            pass

    def grab(self) -> Optional[np.ndarray]:
        if self._camera is None:
            return None
        try:
            frame = self._camera.get_latest_frame()
            if frame is None:
                return None
            return frame  # already BGR uint8
        except Exception as exc:
            logger.warning("[DXGI] Frame grab failed: %s", exc)
            self._camera = None
            return None

    def close(self) -> None:
        try:
            if self._camera is not None:
                self._camera.stop()
                del self._camera
        except Exception:
            pass
        self._camera = None


# ---------------------------------------------------------------------------
# MSS fallback backend
# ---------------------------------------------------------------------------

class MSSBackend(CaptureBackend):
    """
    Cross-platform screen capture via **mss** (``pip install mss``).

    MSS is the most portable option and has no GPU dependency, but it
    reads the framebuffer via the OS, incurring higher CPU overhead and
    being blocked by DRM-protected content.
    """

    name = "mss"

    def __init__(self) -> None:
        self._sct: Optional[object] = None
        self._monitor: Optional[dict] = None
        self._monitor_index: int = 0
        self._target: dict = {"index": 0}
        # Latch so a sustained failure (screen lock / display sleep makes BitBlt
        # raise on *every* grab) logs once instead of at the capture frame rate.
        self._fail_logged: bool = False

    def _ensure_session(self) -> bool:
        """(Re)create the ``mss`` session + resolve the target monitor.

        Shared by :meth:`open` and the self-heal path in :meth:`grab`. mss caches
        a GDI device context on the screen; when that DC is invalidated mid-run
        (workstation lock, display sleep, screensaver, session/desktop switch, or
        a display-mode change) every ``BitBlt`` afterward raises with
        ``ERROR_OPERATION_ABORTED`` ("…aborted because of either a thread exit or
        an application request"). Rebuilding the session gets a fresh, valid DC.
        Returns *True* once ``_sct``/``_monitor`` are usable.
        """
        import mss  # type: ignore[import-untyped]
        # Close any prior session first so a re-open never abandons a live DC.
        self.close()
        # Keep the new session *local* until it's fully validated, and assign it to
        # self._sct only on success. That way a failure anywhere below — including
        # monitor enumeration raising — never leaves a leaked session on the
        # instance for open()/grab() to swallow (the finally releases it).
        sct = mss.mss()
        keep = False
        try:
            monitors = sct.monitors  # type: ignore[union-attr]
            # monitors[0] is the virtual all-screens monitor; real monitors start at 1
            real_monitors = monitors[1:]
            if not real_monitors:
                return False  # nothing to capture (headless/virtual session)
            # Prefer matching by virtual-desktop position (always unique, so a
            # same-resolution monitor is never confused) before falling back to
            # the index. This keeps MSS pointed at the *same physical monitor* the
            # other backends resolved, even when the mss order differs.
            chosen = None
            left, top = self._target.get("left"), self._target.get("top")
            if left is not None and top is not None:
                for mon in real_monitors:
                    if mon.get("left") == left and mon.get("top") == top:
                        chosen = mon
                        break
            if chosen is None:
                # Clamp into range; a negative index would otherwise select from
                # the end of the list via Python's negative indexing.
                idx = min(max(self._monitor_index, 0), len(real_monitors) - 1)
                chosen = real_monitors[idx]
            self._sct = sct
            self._monitor = chosen
            keep = True
            return True
        finally:
            if not keep:
                with suppress(Exception):
                    sct.close()

    def open(self, target, target_size=None, fps_target: int = 30) -> bool:
        self._target = _as_target(target)
        self._monitor_index = int(self._target.get("index", 0))
        try:
            if not self._ensure_session():
                return False
            logger.info("[MSS] Capture initialised for monitor index %d.", self._monitor_index)
            return True
        except Exception as exc:
            logger.debug("[MSS] Not available: %s", exc)
            return False

    def grab(self) -> Optional[np.ndarray]:
        # Lazily (re)build the session — covers both the first grab and recovery
        # after a previous grab tore down a dead DC (see _ensure_session).
        if self._sct is None or self._monitor is None:
            try:
                if not self._ensure_session():
                    return None
            except Exception as exc:
                logger.debug("[MSS] Re-open failed: %s", exc)
                # close() (not bare nulling) so a partially-created session is
                # released rather than leaked, keeping teardown in one place.
                self.close()
                return None
        try:
            import numpy as _np
            shot = self._sct.grab(self._monitor)  # type: ignore[union-attr]
            # shot.rgb is RGB bytes; convert to BGR numpy array
            frame = _np.frombuffer(shot.bgra, dtype=_np.uint8).reshape(
                shot.height, shot.width, 4
            )
            self._fail_logged = False  # delivered again — re-arm the warning
            return frame[:, :, :3]  # drop alpha, keep BGR
        except Exception as exc:
            # Log once per outage, not every frame (see _fail_logged) — otherwise a
            # locked screen floods the log at the capture frame rate.
            if not self._fail_logged:
                logger.warning("[MSS] Frame grab failed: %s", exc)
                self._fail_logged = True
            # Tear down the (now invalid) DC so the next grab rebuilds it instead
            # of failing forever on a stale handle. A transient lock/sleep then
            # self-heals on resume rather than exhausting the backend.
            self.close()
            return None

    def close(self) -> None:
        try:
            if self._sct is not None:
                self._sct.close()  # type: ignore[union-attr]
        except Exception:
            pass
        self._sct = None
        # Null the monitor too so a subsequent grab re-runs _ensure_session
        # rather than reading a stale handle against a freed DC.
        self._monitor = None


# ---------------------------------------------------------------------------
# Capture manager
# ---------------------------------------------------------------------------

class ScreenCaptureManager:
    """
    Manages screen capture with automatic backend selection and failover.

    Backends are tried in the order specified by *method* preference:
    ``wgc`` → ``dxgi`` → ``mss``.  If the active backend produces *None*
    for more than :attr:`_FAIL_THRESHOLD` consecutive frames it is considered
    failed and the next backend is promoted.

    Parameters
    ----------
    preferred_method:
        One of ``"wgc"``, ``"dxgi"``, ``"mss"``.  The manager always tries
        this first, then falls back down the chain.
    monitor_index:
        Zero-based monitor index (0 = primary). Legacy/back-compat shorthand;
        ignored when *target* is given.
    target:
        Resolved monitor identity dict (``{index, id, gdi_name, left, top, …}``)
        from :func:`ambilight.monitors.resolve_monitor`. Preferred over
        *monitor_index* so each backend can re-find the same physical monitor by
        a stable identifier rather than a per-backend index.
    fps_target:
        Target frame rate.  :meth:`grab` will sleep to honour this.
    """

    _FAIL_THRESHOLD = 10
    # Once every backend is exhausted (or the sole backend keeps failing), only
    # re-probe this often instead of every frame. Bounds the failover churn — and
    # its logging — to one attempt per window. Long enough that a transient
    # lock/sleep/display-change is given time to clear; short enough that capture
    # resumes within a few seconds of the screen coming back.
    _COOLDOWN_S = 5.0

    def __init__(
        self,
        preferred_method: str = "wgc",
        monitor_index: int = 0,
        fps_target: int = 30,
        analysis_width: int = 80,
        analysis_height: int = 45,
        target=None,
    ) -> None:
        self._target = _as_target(target if target is not None else monitor_index)
        self._monitor_index = int(self._target.get("index", 0))
        self._fps_target = fps_target
        self._frame_interval = 1.0 / max(fps_target, 1)
        self._target_size = (analysis_width, analysis_height)
        self._last_grab_time: float = 0.0
        self._consecutive_failures: int = 0
        # Cooldown gate (see grab) + a one-shot latch so a sustained outage is
        # reported once, not once per retry. Cleared only when a frame is actually
        # delivered again (see grab) — re-opening a still-dead backend doesn't.
        self._next_retry_at: float = 0.0
        self._degraded_logged: bool = False
        # Non-blocking promotion check: when the active backend is not the
        # highest-priority candidate (e.g. MSS is running while WGC is
        # attempting an auto-restart), check every _COOLDOWN_S whether a
        # better backend has become available without calling open() again.
        self._next_check_at: float = 0.0

        # Ordered backend list, highest priority first. This is the immutable
        # master set: recovery re-probes *all* of these (a backend that failed
        # mid-run — e.g. MSS after a screen lock — can become usable again), so
        # nothing is ever removed from it.
        all_backends: dict[str, CaptureBackend] = {
            "wgc": WGCBackend(),
            "dxgi": DXGIBackend(),
            "mss": MSSBackend(),
        }
        order = [preferred_method] + [k for k in all_backends if k != preferred_method]
        self._candidates: list[CaptureBackend] = [all_backends[k] for k in order]
        self._active: Optional[CaptureBackend] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the highest-priority available backend."""
        self._active = None
        backend = self._open_best()
        if backend is None:
            raise RuntimeError(
                "No screen capture backend could be initialised.  "
                "Ensure mss is installed: pip install mss"
            )
        self._consecutive_failures = 0
        self._degraded_logged = False
        logger.info("[Capture] Active backend: %s", backend.name.upper())
        self._warn_if_degraded(backend)

    def _open_best(self, *, require_frame: bool = False) -> Optional[CaptureBackend]:
        """Open the first available backend in priority order and make it active.

        Pure mechanism: sets ``_active`` and returns the backend (or *None* if
        none open). Deliberately does **no** logging or latch bookkeeping so the
        recovery path can decide what's worth announcing — re-opening a still-dead
        sole backend mid-outage must stay quiet to keep a 24/7 log clean.

        When ``require_frame`` is set, a backend must also deliver a frame to be
        accepted; one that opens but yields nothing (e.g. a locked screen) is
        closed and skipped. Recovery uses this so a dead high-priority backend
        can't keep winning the re-probe and starving a working fallback.
        """
        for backend in self._candidates:
            try:
                opened = backend.open(self._target, self._target_size, self._fps_target)
            except Exception as exc:  # defensive — a backend should never raise here
                logger.debug("[Capture] %s.open() raised: %s", backend.name, exc)
                opened = False
            if not opened:
                continue
            if require_frame and not self._delivers_frame(backend):
                with suppress(Exception):
                    backend.close()
                continue
            self._active = backend
            return backend
        self._active = None
        return None

    @staticmethod
    def _delivers_frame(backend: CaptureBackend) -> bool:
        """True if *backend* yields a frame right now. Used to confirm a recovered
        backend is actually working, not merely open."""
        try:
            return backend.grab() is not None
        except Exception:
            return False

    def _warn_if_degraded(self, backend: CaptureBackend) -> None:
        """Loudly flag a fallback to MSS on Windows.

        MSS uses GDI/BitBlt, which renders **black** for exclusive-fullscreen
        games and hardware-accelerated overlay video — the exact "lights don't
        react to my game" symptom. If we landed on MSS on Windows it means
        ``windows-capture`` (WGC) and ``dxcam`` (DXGI) are both unavailable; tell
        the user how to fix it rather than silently degrading.
        """
        import sys
        if backend.name == "mss" and sys.platform == "win32":
            logger.warning(
                "[Capture] Using the MSS backend on Windows — fullscreen games "
                "and hardware-overlay video will appear BLACK. Install the WGC "
                "backend for proper capture: pip install windows-capture "
                "(optional DXGI fallback: pip install dxcam)."
            )

    def stop(self) -> None:
        """Close the active backend."""
        if self._active is not None:
            self._active.close()
            self._active = None

    # ------------------------------------------------------------------
    # Grab
    # ------------------------------------------------------------------

    def grab(self) -> Optional[np.ndarray]:
        """
        Capture one frame, rate-limiting to :attr:`fps_target`.

        Returns
        -------
        numpy.ndarray or None
            BGR uint8 frame, or *None* if all backends are exhausted.
        """
        # Monotonic rate limiting — sleep the whole remaining interval in one go.
        # (A previous busy spin-wait burned a CPU core; a plain sleep is plenty
        # accurate for a 24/7 LED tool and keeps idle CPU low.)
        delay = (self._last_grab_time + self._frame_interval) - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last_grab_time = time.monotonic()

        frame = self._active.grab() if self._active else None

        if frame is not None:
            # A delivered frame is the only thing that clears the degraded latch,
            # so a backend that re-opens but still returns nothing won't reset it
            # and re-announce on the next cooldown.
            self._consecutive_failures = 0
            self._degraded_logged = False
            # Periodically check whether a higher-priority backend has become
            # available (e.g. WGC auto-restarted after a game dropped exclusive
            # fullscreen). Non-blocking: calls grab() on candidates without
            # open() — only the auto-restart worker calls open() in background.
            now = time.monotonic()
            if self._active is not self._candidates[0] and now >= self._next_check_at:
                self._next_check_at = now + self._COOLDOWN_S
                better = self._find_ready_candidate()
                if better is not None:
                    logger.info(
                        "[Capture] Promoting from %s to %s.",
                        self._active.name.upper(),
                        better.name.upper(),
                    )
                    with suppress(Exception):
                        self._active.close()
                    self._active = better
            return frame

        # No frame this round (active backend stalled, or already exhausted).
        self._consecutive_failures += 1
        now = time.monotonic()
        # Recover at most once per cooldown — whether the active backend just
        # stalled or we're already exhausted and re-probing. This is what keeps a
        # transient capture failure from turning into an unbounded retry/log storm
        # (previously every frame re-tripped the switch, spamming "Backend '?'
        # failed / All backends exhausted" ~2×/s). The active backend's own
        # transient recovery (e.g. MSS rebuilding a dead DC) usually resolves
        # things before the threshold is even reached.
        if self._consecutive_failures >= self._FAIL_THRESHOLD and now >= self._next_retry_at:
            self._next_retry_at = now + self._COOLDOWN_S
            self._attempt_recovery()
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _attempt_recovery(self) -> None:
        """Re-probe the backends after the active one has stalled.

        Called at most once per :attr:`_COOLDOWN_S` from :meth:`grab`. Closes the
        stalled backend and re-opens the best available, re-probing *all*
        candidates because a mid-run failure is often transient (a screen lock or
        display-sleep invalidates MSS's device context; it works again once the
        screen is back). Logging is latched: a switch to a *different* backend, or
        recovery after an outage, is announced; a sole dead backend silently
        re-opening each cooldown is not, and a full outage is logged once.
        ``is_healthy`` stays False throughout because the failure counter is only
        cleared by an actually-delivered frame (see :meth:`grab`).
        """
        previous = self._active
        previous_name = previous.name if previous is not None else None
        if previous is not None:
            with suppress(Exception):
                previous.close()
            self._active = None

        # Require a delivered frame: a backend that re-opens but yields nothing
        # (still-locked screen) must not be reselected over a working fallback.
        backend = self._open_best(require_frame=True)
        if backend is not None:
            # Announce a real change (a different backend) or a recovery (we'd
            # already logged an outage). Stay silent when the same sole backend
            # merely re-opened mid-outage — that would flood a 24/7 log.
            if backend.name != previous_name or self._degraded_logged:
                logger.info("[Capture] Active backend: %s", backend.name.upper())
                self._warn_if_degraded(backend)
                self._degraded_logged = False
            return

        # Nothing opened — fully exhausted. Log once per outage.
        if not self._degraded_logged:
            logger.error(
                "[Capture] All backends exhausted — no capture source available. "
                "Retrying every %.0fs.", self._COOLDOWN_S,
            )
            self._degraded_logged = True

    def _find_ready_candidate(self) -> Optional[CaptureBackend]:
        """Non-blocking probe for a higher-priority backend that is already
        open and delivering frames.

        Does **not** call ``open()`` — it only calls ``grab()`` on each
        candidate ranked above the current active backend.  Returns the first
        candidate that delivers a non-None frame, or ``None`` if none do.

        This is the counterpart to :meth:`WGCBackend._restart_worker`: the
        worker calls ``open()`` in the background; this method notices that
        WGC is back by observing a non-None ``grab()`` result, and the manager
        promotes without any blocking call.
        """
        if self._active is None:
            return None
        try:
            active_pos = self._candidates.index(self._active)
        except ValueError:
            return None
        if active_pos == 0:
            return None  # already on the highest-priority backend
        for candidate in self._candidates[:active_pos]:
            try:
                frame = candidate.grab()
                if frame is not None:
                    return candidate
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def active_backend(self) -> Optional[str]:
        """Name of the backend currently in use (``"wgc"``/``"dxgi"``/``"mss"``),
        or ``None`` if every backend has been exhausted."""
        return self._active.name if self._active is not None else None

    @property
    def is_healthy(self) -> bool:
        """True while a backend is open and delivering frames.

        Goes False when all backends are exhausted, or when the active backend
        has returned ``None`` for a sustained run (``_FAIL_THRESHOLD``) — i.e.
        capture is producing nothing, which is what freezes the LEDs."""
        return self._active is not None and self._consecutive_failures < self._FAIL_THRESHOLD
