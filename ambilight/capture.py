"""
Screen Capture Module
=====================
Provides a unified :class:`ScreenCaptureManager` that selects the fastest
available capture backend at runtime and automatically falls back when a
backend fails mid-run.

Backend priority
----------------
1. **Windows Graphics Capture API** (``wgc``) — lowest latency, DRM bypass on
   many titles because it captures the compositor surface rather than reading
   framebuffer.  Requires Windows 10 1903+ and ``winsdk`` / ``winrt`` Python
   bindings.
2. **DXGI Desktop Duplication** (``dxgi``) — very fast, GPU-native, no DRM
   bypass.  Requires ``comtypes`` + ``pywin32`` or ``d3dshot`` / ``dxcam``.
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
# dxcam private-API isolation (TD-05 / R-01)
# ---------------------------------------------------------------------------
# The WGC backend needs a D3D11 device and a texture→numpy mapper. dxcam does
# not expose these publicly, so we reach into ``dxcam._core``. To keep that
# fragility contained — and to fail over cleanly to DXGI/MSS if a dxcam update
# changes its internals — every private access goes through these guarded
# helpers, which raise a clean RuntimeError that callers already handle.

def _dxcam_core():
    """Return the dxcam internals module across versions (``core`` or ``_core``).

    NOTE (TD-05 / R-01): dxcam ≥ 0.3.0 rewrote its internals and no longer
    exposes ``create_d3d_device`` / ``frame_to_numpy`` at all, so the WGC backend
    cannot borrow a D3D device from dxcam on those versions and will fail over to
    DXGI/MSS. These helpers stay defensive so older dxcam builds keep working and
    newer ones degrade gracefully rather than crash.
    """
    import importlib
    for name in ("dxcam.core", "dxcam._core"):
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    raise RuntimeError("dxcam internals module not found")


def _wgc_create_d3d_device() -> object:
    """Create a D3D11 device for WGC. Raises RuntimeError if unavailable."""
    try:
        core = _dxcam_core()
        return core.create_d3d_device()  # type: ignore[attr-defined]
    except Exception as exc:  # ImportError or dxcam internal change
        raise RuntimeError(f"dxcam D3D device unavailable: {exc}") from exc


def _wgc_frame_to_numpy(frame: object, device: object) -> np.ndarray:
    """Map a WGC D3D texture to a numpy array. Raises RuntimeError on failure."""
    try:
        core = _dxcam_core()
        return core.frame_to_numpy(frame, device)  # type: ignore[attr-defined]
    except Exception as exc:
        raise RuntimeError(f"dxcam frame mapping unavailable: {exc}") from exc


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

class WGCBackend(CaptureBackend):
    """
    Windows Graphics Capture API backend.

    Uses ``winsdk`` (``pip install winsdk``) to access
    ``Windows.Graphics.Capture``.  Falls back gracefully when unavailable.

    Notes
    -----
    WGC captures the GPU compositor surface which includes HDR content and, on
    many DRM-protected streaming applications, the decoded video frame — making
    it the preferred backend for Ambilight use with Netflix, Disney+, etc.
    """

    name = "wgc"

    def __init__(self) -> None:
        self._session: Optional[object] = None
        self._frame_pool: Optional[object] = None
        self._item: Optional[object] = None
        self._available = False
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()

    def open(self, monitor_index: int) -> bool:  # noqa: C901
        try:
            # WGC requires Windows 10 1903 build 18362+
            import sys
            if sys.platform != "win32":
                return False

            # Lazy imports – these will ImportError on non-Windows or if winsdk
            # is not installed
            from winsdk.windows.graphics.capture import (  # type: ignore[import-untyped]
                Direct3D11CaptureFramePool,
                GraphicsCaptureSession,
            )
            from winsdk.windows.graphics.directx import DirectXPixelFormat  # type: ignore[import-untyped]
            from winsdk.windows.graphics.directx.direct3d11 import (  # type: ignore[import-untyped]
                IDirect3DDevice,
            )
            import ctypes, ctypes.wintypes

            # Enumerate display monitors via EnumDisplayMonitors so we can
            # build a GraphicsCaptureItem from the correct HMONITOR.
            monitors: list[int] = []

            def _enum_cb(hmon: int, _hdc: int, _rect: object, _lparam: int) -> bool:
                monitors.append(hmon)
                return True

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.wintypes.RECT),
                ctypes.c_double,
            )
            cb = MonitorEnumProc(_enum_cb)
            ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)  # type: ignore[attr-defined]

            if monitor_index >= len(monitors):
                monitor_index = 0

            hmonitor = monitors[monitor_index]

            # winsdk ≥ 1.0.0b10 exposes a public interop helper that builds a
            # GraphicsCaptureItem straight from an HMONITOR — no comtypes / no
            # IGraphicsCaptureItemInterop (which this winsdk build no longer
            # exports, the cause of the previous silent WGC failure).
            from winsdk.windows.graphics.capture.interop import (  # type: ignore[import-untyped]
                create_for_monitor,
            )

            item = create_for_monitor(hmonitor)

            # Create a D3D11 device (dxcam private API, isolated + guarded)
            device = _wgc_create_d3d_device()

            size = item.Size
            frame_pool = Direct3D11CaptureFramePool.Create(
                device,
                DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,
                1,
                size,
            )
            session = GraphicsCaptureSession(frame_pool, item)
            session.IsCursorCaptureEnabled = False
            session.IsBorderRequired = False
            session.Start()

            self._frame_pool = frame_pool
            self._session = session
            self._item = item
            self._device = device
            self._available = True
            logger.info("[WGC] Capture session started for monitor %d.", monitor_index)
            return True

        except Exception as exc:
            logger.debug("[WGC] Not available: %s", exc)
            return False

    def grab(self) -> Optional[np.ndarray]:
        if not self._available or self._frame_pool is None:
            return None
        try:
            frame = self._frame_pool.TryGetNextFrame()
            if frame is None:
                return None

            # Map the Direct3D texture to a numpy array (guarded dxcam access)
            arr = _wgc_frame_to_numpy(frame, self._device)
            # arr is BGRA; drop alpha channel
            return arr[:, :, :3]
        except Exception as exc:
            logger.warning("[WGC] Frame grab failed: %s", exc)
            self._available = False
            return None

    def close(self) -> None:
        try:
            if self._session is not None:
                self._session.Close()
            if self._frame_pool is not None:
                self._frame_pool.Close()
        except Exception:
            pass
        self._session = None
        self._frame_pool = None
        self._available = False


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
