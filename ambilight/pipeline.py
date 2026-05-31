"""
Ambilight Pipeline Module
=========================
The :class:`AmbilightPipeline` orchestrates all subsystems into a coherent,
production-grade Ambilight engine:

1. **Screen capture** — grabs frames via the best available backend.
2. **GPU resize** — downscales to analysis resolution on GPU or CPU.
3. **Zone decomposition** — slices the frame into configurable edge zones.
4. **Colour analysis** — extracts the dominant/weighted colour per zone.
5. **Smoothing** — applies adaptive EMA to eliminate flicker.
6. **LED output** — transmits the final colour to the MagicHome controller.
7. **Metrics** — records FPS and end-to-end latency.

The pipeline runs in a tight loop on the calling thread.  Call
:meth:`run` from a dedicated thread or the main thread and call
:meth:`stop` from another thread (or a signal handler) to shut down.

Signal handling
---------------
``SIGINT`` and ``SIGTERM`` are caught and translated into a graceful stop so
the LED controller can be turned off cleanly before the process exits.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Optional

import numpy as np

from .capture import ScreenCaptureManager
from .color import ColorAnalyzer
from .config import AppConfig, ConfigManager
from .discovery import DeviceDiscovery, DeviceInfo
from .gpu import GpuAccelerator, detect_backend
from .led_output import MagicHomeController
from .logging_setup import PerformanceMetrics, setup_logging
from .smoothing import SmoothingEngine
from .zones import ZoneManager

logger = logging.getLogger(__name__)


class AmbilightPipeline:
    """
    Top-level Ambilight engine.

    Instantiate with a loaded :class:`AppConfig`, call :meth:`start` to
    initialise subsystems, then :meth:`run` to enter the main loop.

    Parameters
    ----------
    config:
        Application configuration.  Defaults to ``ConfigManager.get()``.
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._cfg = config or ConfigManager.get()
        self._running = False
        self._metrics: Optional[PerformanceMetrics] = None

        # Sub-system instances (populated in start())
        self._capture: Optional[ScreenCaptureManager] = None
        self._gpu: Optional[GpuAccelerator] = None
        self._zones: Optional[ZoneManager] = None
        self._analyzer: Optional[ColorAnalyzer] = None
        self._smoother: Optional[SmoothingEngine] = None
        self._led: Optional[MagicHomeController] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Initialise all subsystems.

        This must be called before :meth:`run`.  It is separated from
        ``__init__`` so that initialisation errors surface before the caller
        commits to the event loop.
        """
        cfg = self._cfg
        log_cfg = cfg.logging

        # Logging
        self._metrics = setup_logging(
            level=log_cfg.level,
            log_file=log_cfg.file,
            max_bytes=log_cfg.max_bytes,
            backup_count=log_cfg.backup_count,
            show_fps=log_cfg.show_fps,
            fps_interval=log_cfg.fps_interval,
        )
        logger.info("=" * 60)
        logger.info("  Ambilight Engine  starting up …")
        logger.info("=" * 60)

        # GPU
        backend = detect_backend(
            prefer=cfg.gpu.prefer,
            fallback_to_cpu=cfg.gpu.fallback_to_cpu,
        ) if cfg.gpu.enabled else None
        from .gpu import GpuBackend
        self._gpu = GpuAccelerator(backend if backend is not None else GpuBackend.CPU)

        # Screen capture
        self._capture = ScreenCaptureManager(
            preferred_method=cfg.capture.method,
            monitor_index=cfg.capture.monitor_index,
            fps_target=cfg.capture.fps_target,
        )
        self._capture.start()

        # Zone manager
        z = cfg.zones
        self._zones = ZoneManager(
            n_top=z.top,
            n_bottom=z.bottom,
            n_left=z.left,
            n_right=z.right,
        )

        # Colour analyser
        c = cfg.color
        self._analyzer = ColorAnalyzer(
            mode=c.mode,
            black_threshold=c.ignore_black_threshold,
            white_threshold=c.ignore_white_threshold,
            kmeans_clusters=c.kmeans_clusters,
            saturation_weight_power=c.saturation_weight_power,
            min_saturation=c.min_saturation,
        )

        # Smoothing engine
        s = cfg.smoothing
        self._smoother = SmoothingEngine(
            enabled=s.enabled,
            base_alpha=s.base_alpha,
            fast_alpha=s.adaptive_fast_alpha,
            fast_threshold=s.adaptive_fast_threshold,
            min_change=s.min_change,
        )

        # Device discovery + LED controller
        dev_cfg = cfg.device
        device_info = self._discover_device(dev_cfg)
        ip = device_info.ip if device_info else dev_cfg.ip
        self._led = MagicHomeController(
            ip=ip,
            port=dev_cfg.port,
            connect_timeout=dev_cfg.connect_timeout,
            send_timeout=dev_cfg.send_timeout,
            reconnect_interval=dev_cfg.reconnect_interval,
            min_update_interval=1.0 / max(cfg.capture.fps_target, 1),
        )
        if not self._led.connect():
            logger.warning(
                "[Pipeline] Could not connect to LED controller at %s; "
                "will retry during run loop.",
                ip,
            )
        else:
            self._led.turn_on()

        # Signal handlers
        self._install_signal_handlers()
        logger.info("[Pipeline] All subsystems ready.")

    def run(self) -> None:
        """
        Enter the main capture → analyse → output loop.

        Blocks until :meth:`stop` is called or an unrecoverable error occurs.
        """
        if self._capture is None:
            raise RuntimeError("call start() before run()")

        self._running = True
        logger.info("[Pipeline] Main loop running.")

        w = self._cfg.capture.analysis_width
        h = self._cfg.capture.analysis_height

        try:
            while self._running:
                t0 = time.monotonic()

                # --- Capture ---
                frame = self._capture.grab()
                if frame is None:
                    time.sleep(0.01)
                    continue

                # --- Resize to analysis resolution ---
                small: np.ndarray = self._gpu.resize(frame, w, h)  # type: ignore[union-attr]

                # --- Zone decomposition ---
                zone_regions = self._zones.extract_regions(small)  # type: ignore[union-attr]

                # --- Colour analysis ---
                zone_colors = self._analyzer.analyze_zones(zone_regions)  # type: ignore[union-attr]

                # --- Smoothing ---
                smoothed_zones = self._smoother.smooth_zones(zone_colors)  # type: ignore[union-attr]

                # --- Combine zones → single RGB (MagicHome is single-zone) ---
                combined = self._analyzer.combine_zone_colors(smoothed_zones)  # type: ignore[union-attr]
                final_color = self._smoother.smooth_combined(combined)  # type: ignore[union-attr]

                # --- LED output ---
                r, g, b = final_color
                sent = self._led.set_rgb(r, g, b)  # type: ignore[union-attr]

                # --- Metrics ---
                latency_ms = (time.monotonic() - t0) * 1000.0
                if self._metrics is not None:
                    self._metrics.record_frame(latency_ms)

                logger.debug(
                    "[Pipeline] RGB=(%3d,%3d,%3d) | latency=%.1f ms | sent=%s",
                    r, g, b, latency_ms, sent,
                )

        except KeyboardInterrupt:
            logger.info("[Pipeline] KeyboardInterrupt received.")
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Signal the run loop to exit on its next iteration."""
        logger.info("[Pipeline] Stop requested.")
        self._running = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_device(self, dev_cfg: object) -> Optional[DeviceInfo]:
        """Run device discovery and return the best match."""
        discovery = DeviceDiscovery(
            preferred_ip=dev_cfg.ip,  # type: ignore[attr-defined]
            preferred_mac=dev_cfg.mac,  # type: ignore[attr-defined]
            subnet=dev_cfg.subnet,  # type: ignore[attr-defined]
            connect_timeout=dev_cfg.connect_timeout,  # type: ignore[attr-defined]
            discovery_timeout=dev_cfg.discovery_timeout,  # type: ignore[attr-defined]
            cache_file=dev_cfg.cache_file,  # type: ignore[attr-defined]
        )
        try:
            return discovery.find_device()
        except Exception as exc:
            logger.warning("[Pipeline] Device discovery error: %s", exc)
            return None

    def _shutdown(self) -> None:
        """Gracefully release all resources."""
        logger.info("[Pipeline] Shutting down …")

        if self._led is not None:
            try:
                self._led.set_rgb(0, 0, 0)
                self._led.turn_off()
            except Exception:
                pass
            self._led.disconnect()

        if self._capture is not None:
            self._capture.stop()

        if self._metrics is not None:
            self._metrics.stop()

        logger.info("[Pipeline] Shutdown complete.")

    def _install_signal_handlers(self) -> None:
        """Register SIGINT / SIGTERM handlers for clean shutdown."""
        def _handler(signum: int, _frame: object) -> None:
            logger.info("[Pipeline] Signal %d received — stopping.", signum)
            self.stop()

        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
