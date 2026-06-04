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
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------

class CaptureBackend(ABC):
    """Interface that all capture backends must implement."""

    name: str = "base"

    @abstractmethod
    def open(self, monitor_index: int) -> bool:
        """
        Initialise the backend for *monitor_index*.

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

def _bgra_to_bgr(buffer: np.ndarray) -> np.ndarray:
    """Convert a WGC ``frame_buffer`` (H×W×4 BGRA) to a contiguous H×W×3 BGR array.

    The library reuses its buffer between callbacks, so the result is copied to
    decouple it from the capture thread.
    """
    arr = np.asarray(buffer)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        arr = arr[:, :, :3]
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
    """

    name = "wgc"

    def __init__(self) -> None:
        self._control: Optional[object] = None
        self._available = False
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def _store_frame(self, buffer: np.ndarray) -> None:
        """Callback sink: stash the most recent frame as contiguous BGR."""
        bgr = _bgra_to_bgr(buffer)
        with self._lock:
            self._latest_frame = bgr

    def open(self, monitor_index: int) -> bool:
        try:
            import sys
            if sys.platform != "win32":
                return False

            # Lazy import — ImportError on non-Windows or if the package/native
            # extension is missing, which the manager handles by failing over.
            from windows_capture import WindowsCapture  # type: ignore[import-untyped]

            # windows-capture monitor_index is 1-based; our config is 0-based.
            capture = WindowsCapture(
                cursor_capture=False,
                draw_border=False,
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

            self._control = capture.start_free_threaded()
            self._available = True
            logger.info("[WGC] Capture session started for monitor %d.", monitor_index)
            return True

        except Exception as exc:
            logger.debug("[WGC] Not available: %s", exc)
            return False

    def grab(self) -> Optional[np.ndarray]:
        if not self._available:
            return None
        with self._lock:
            return self._latest_frame  # BGR uint8, or None until the first frame

    def close(self) -> None:
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

    def __init__(self) -> None:
        self._camera: Optional[object] = None

    def open(self, monitor_index: int) -> bool:
        try:
            import sys
            if sys.platform != "win32":
                return False

            import dxcam  # type: ignore[import-untyped]
            self._camera = dxcam.create(output_idx=monitor_index, output_color="BGR")
            self._camera.start(target_fps=60, video_mode=True)
            logger.info("[DXGI] dxcam capture started for monitor %d.", monitor_index)
            return True
        except Exception as exc:
            logger.debug("[DXGI] Not available: %s", exc)
            return False

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

    def open(self, monitor_index: int) -> bool:
        try:
            import mss  # type: ignore[import-untyped]
            self._sct = mss.mss()
            monitors = self._sct.monitors  # type: ignore[union-attr]
            # monitors[0] is the virtual all-screens monitor; real monitors start at 1
            real_monitors = monitors[1:]
            if not real_monitors:
                return False
            idx = min(monitor_index, len(real_monitors) - 1)
            self._monitor = real_monitors[idx]
            logger.info("[MSS] Capture initialised for monitor %d.", monitor_index)
            return True
        except Exception as exc:
            logger.debug("[MSS] Not available: %s", exc)
            return False

    def grab(self) -> Optional[np.ndarray]:
        if self._sct is None or self._monitor is None:
            return None
        try:
            import numpy as _np
            shot = self._sct.grab(self._monitor)  # type: ignore[union-attr]
            # shot.rgb is RGB bytes; convert to BGR numpy array
            frame = _np.frombuffer(shot.bgra, dtype=_np.uint8).reshape(
                shot.height, shot.width, 4
            )
            return frame[:, :, :3]  # drop alpha, keep BGR
        except Exception as exc:
            logger.warning("[MSS] Frame grab failed: %s", exc)
            return None

    def close(self) -> None:
        try:
            if self._sct is not None:
                self._sct.close()  # type: ignore[union-attr]
        except Exception:
            pass
        self._sct = None


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
        Zero-based monitor index (0 = primary).
    fps_target:
        Target frame rate.  :meth:`grab` will sleep to honour this.
    """

    _FAIL_THRESHOLD = 10

    def __init__(
        self,
        preferred_method: str = "wgc",
        monitor_index: int = 0,
        fps_target: int = 30,
    ) -> None:
        self._monitor_index = monitor_index
        self._fps_target = fps_target
        self._frame_interval = 1.0 / max(fps_target, 1)
        self._last_grab_time: float = 0.0
        self._consecutive_failures: int = 0

        # Build ordered candidate list
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
        for backend in self._candidates:
            if backend.open(self._monitor_index):
                self._active = backend
                logger.info(
                    "[Capture] Active backend: %s", backend.name.upper()
                )
                return
        raise RuntimeError(
            "No screen capture backend could be initialised.  "
            "Ensure mss is installed: pip install mss"
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
        # Monotonic rate limiting (spin-wait for precision)
        target_time = self._last_grab_time + self._frame_interval
        while True:
            now = time.monotonic()
            if now >= target_time:
                break
            remaining = target_time - now
            if remaining > 0.002:
                time.sleep(0.001)
            else:
                pass  # Spin wait for the last ~2ms to avoid oversleeping
        self._last_grab_time = time.monotonic()

        frame = self._active.grab() if self._active else None

        if frame is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._FAIL_THRESHOLD:
                logger.warning(
                    "[Capture] Backend '%s' failed %d times; switching.",
                    self._active.name if self._active else "?",
                    self._consecutive_failures,
                )
                self._switch_backend()
            return None

        self._consecutive_failures = 0
        return frame

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _switch_backend(self) -> None:
        """Close the current backend and promote the next candidate."""
        if self._active is not None:
            self._active.close()
            try:
                self._candidates.remove(self._active)
            except ValueError:
                pass
            self._active = None

        self._consecutive_failures = 0

        for backend in self._candidates:
            if backend.open(self._monitor_index):
                self._active = backend
                logger.info(
                    "[Capture] Switched to backend: %s", backend.name.upper()
                )
                return

        logger.error("[Capture] All backends exhausted — no capture source available.")
