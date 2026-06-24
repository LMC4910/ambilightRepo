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
from collections import deque
from dataclasses import dataclass, field as dc_field
from typing import Optional

import numpy as np

from .capture import ScreenCaptureManager, is_black_frame
from .color import ColorAnalyzer
from .hdr import HdrDetector
from .tonemap import tonemap_bgr
from .config import AppConfig, ConfigManager
from .discovery import DeviceDiscovery, DeviceInfo
from .gpu import GpuAccelerator, detect_backend
from .devices import LedDriver, create_driver
from .logging_setup import PerformanceMetrics, setup_logging
from .smoothing import SmoothingEngine
from .zones import ZoneManager
from .effects_engine import EffectsManager, EffectScheduler
from .gradient_engine import generate_gradient

logger = logging.getLogger(__name__)

# Consecutive screen-sync iterations of all-black-but-delivering capture before
# we flag it as no-signal. At the default 30 FPS target this is ~2 s — long
# enough that a real fade-to-black scene won't trip it, short enough that a
# stuck/DRM/MSS-fullscreen black-out is surfaced promptly.
_BLACK_NOSIGNAL_FRAMES: int = 60

# Capture backends (WGC/DXGI especially) occasionally emit a single spurious
# all-black frame even when the screen content is unchanged. Pushing that
# straight to the strip makes the lights blink off for a frame on an otherwise
# static screen. Hold the last colour for up to this many consecutive black
# frames before honouring black, so a lone glitch frame is invisible while a
# genuinely black screen still goes dark within ~this/fps seconds.
_BLACK_DEBOUNCE_FRAMES: int = 3


def _nosignal_verdict(consecutive_black: int, backend: Optional[str]) -> tuple[bool, str]:
    """Classify a run of consecutive all-black-but-delivering frames.

    Returns ``(capture_ok, capture_reason)``. Below the sustained threshold this
    is ``(True, "ok")`` — a brief dark scene is not a fault. At/above it capture
    is effectively dead: WGC/DXGI can see fullscreen games, so persistent black
    there is almost always DRM-protected content (``drm_suspected``); on MSS it
    is the fullscreen game itself rendering black (``black``).
    """
    if consecutive_black >= _BLACK_NOSIGNAL_FRAMES:
        return False, ("black" if backend == "mss" else "drm_suspected")
    return True, "ok"


@dataclass
class _Channel:
    """One device + its own analysis chain, bound to a monitor.

    Multiple channels may share a monitor's captured frame; each owns its LED
    controller, zone manager, analyser and smoother so per-device state is
    independent.
    """
    name: str
    monitor_index: int
    led: LedDriver
    zones: "ZoneManager"
    analyzer: "ColorAnalyzer"
    smoother: "SmoothingEngine"
    led_count: int
    last_zone_colors: list = dc_field(default_factory=list)
    black_streak: int = 0   # consecutive black frames seen (transient-black debounce)
    last_output_rgb: tuple = (0, 0, 0)   # this channel's last real colour (flash restore)


def _device_specs(cfg) -> list[dict]:
    """Normalise config into a list of device specs.

    Uses ``cfg.devices`` (multi-device) when non-empty, otherwise falls back to
    the single ``cfg.device`` bound to ``cfg.capture.monitor_index`` (back-compat).
    """
    import dataclasses
    raw = list(getattr(cfg, "devices", None) or [])
    dev = cfg.device
    specs: list[dict] = []

    def _resolve_port(proto: str, explicit) -> int:
        """Pick the control port for *proto*, protocol-aware.

        WLED is controlled over its HTTP API (default 80); 5577 is the MagicHome
        TCP port AND the legacy ``device.port`` default. The UI/onboarding persist
        no port for WLED, so the entry inherits 5577 — which must NOT become the
        WLED HTTP port (the pipeline would probe ``http://<ip>:5577/json/info``
        and never connect). Treat an unset/5577 port as "use WLED's default 80".
        """
        try:
            explicit = int(explicit) if explicit else 0
        except (TypeError, ValueError):
            explicit = 0
        if proto == "wled":
            return explicit if explicit and explicit != 5577 else 80
        return explicit or int(dev.port)

    if raw:
        for d in raw:
            d = d if isinstance(d, dict) else dataclasses.asdict(d)
            if not d.get("enabled", True):
                continue
            proto = str(d.get("protocol", getattr(dev, "protocol", "magichome"))).lower()
            specs.append({
                "ip": d.get("ip", ""),
                "mac": d.get("mac", ""),
                "port": _resolve_port(proto, d.get("port")),
                "monitor_index": int(d.get("monitor_index", 0)),
                "monitor_id": str(d.get("monitor_id") or ""),
                "led_count": int(d.get("led_count", 30)),
                "name": d.get("name") or d.get("ip") or "device",
                "protocol": proto,
                "connect_timeout": float(d.get("connect_timeout", dev.connect_timeout)),
                "send_timeout": float(d.get("send_timeout", dev.send_timeout)),
                "reconnect_interval": float(d.get("reconnect_interval", dev.reconnect_interval)),
                "subnet": d.get("subnet", dev.subnet),
                "discovery_timeout": float(d.get("discovery_timeout", dev.discovery_timeout)),
                "cache_file": d.get("cache_file", dev.cache_file),
            })
    else:
        proto = str(getattr(dev, "protocol", "magichome")).lower()
        specs.append({
            "ip": dev.ip, "mac": dev.mac, "port": _resolve_port(proto, dev.port),
            "monitor_index": cfg.capture.monitor_index,
            # Prefer a device-level stable id (matches the multi-device path),
            # falling back to the global capture id when the device sets none.
            "monitor_id": getattr(dev, "monitor_id", "") or cfg.capture.monitor_id,
            "led_count": getattr(dev, "led_count", 30),
            "name": getattr(dev, "name", "") or dev.ip,
            "protocol": proto,
            "connect_timeout": dev.connect_timeout, "send_timeout": dev.send_timeout,
            "reconnect_interval": dev.reconnect_interval, "subnet": dev.subnet,
            "discovery_timeout": dev.discovery_timeout, "cache_file": dev.cache_file,
        })
    return specs


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

    def __init__(self, config: Optional[AppConfig] = None, stop_event=None, pause_event=None, metrics_queue=None, command_queue=None) -> None:
        self._cfg = config or ConfigManager.get()
        self._running = False
        self._metrics: Optional[PerformanceMetrics] = None
        self._stop_event = stop_event
        self._pause_event = pause_event
        self._metrics_queue = metrics_queue
        self._command_queue = command_queue

        # Sub-system instances (populated in start())
        self._gpu: Optional[GpuAccelerator] = None
        # Multi-device I/O: one capture per distinct monitor, one channel per device.
        self._captures: dict[int, ScreenCaptureManager] = {}
        # raw (config) monitor index -> live index the backend opened, for HDR lookups.
        self._resolved_index: dict[int, int] = {}
        self._channels: list[_Channel] = []
        self._topology: Optional[tuple] = None
        self._effects: EffectsManager = EffectsManager()
        self._scheduler: Optional[EffectScheduler] = None
        self._scheduled_active: bool = False
        self._last_sched_check: float = 0.0
        self._hdr: Optional[HdrDetector] = None
        self._last_hdr_check: float = 0.0
        self._start_time: float = time.monotonic()
        self._last_zone_colors: list = []
        self._last_debug_log: float = 0.0
        # Sustained-black detection: count consecutive screen-sync iterations
        # where capture delivers frames but they are all (near-)black, so the UI
        # can report *why* the strip went dark instead of masquerading as healthy.
        self._consecutive_black: int = 0
        self._power: bool = True               # strip powered on?
        self._mode: str = "screen_sync"        # reported mode ("off" when powered off)
        # Notification-flash overlay: transient blinks that briefly override the
        # strip then restore the prior frame. Bounded deque coalesces bursts.
        self._flash_queue: deque = deque(maxlen=3)
        self._flash_active: Optional[dict] = None
        self._last_output_rgb: tuple = (0, 0, 0)   # last real colour, for restore

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
            file_level=getattr(log_cfg, "file_level", "INFO"),
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

        # Captures (per monitor) + device channels.
        self._build_io()

        # HDR detector: per-monitor advanced-color state, so the capture path can
        # tone-map washed HDR frames back to SDR before colour analysis.
        self._hdr = HdrDetector()

        # Effects: load plugins + build the schedule.
        import os
        eff_cfg = getattr(cfg, "effects", None)
        plugins_dir = (eff_cfg.plugins_dir if eff_cfg and eff_cfg.plugins_dir
                       else os.path.join(os.path.expanduser("~"), ".ambilight", "plugins"))
        try:
            self._effects.load_plugins(plugins_dir)
        except Exception as exc:
            logger.warning("[Pipeline] Plugin load error: %s", exc)
        self._scheduler = EffectScheduler(eff_cfg.schedule if eff_cfg else [])

        # Signal handlers
        self._install_signal_handlers()
        logger.info("[Pipeline] All subsystems ready.")

    def run(self) -> None:
        """
        Enter the main capture → analyse → output loop.

        Blocks until :meth:`stop` is called or an unrecoverable error occurs.
        """
        if not self._channels:
            raise RuntimeError("call start() before run()")

        self._running = True
        logger.info("[Pipeline] Main loop running.")

        w = self._cfg.capture.analysis_width
        h = self._cfg.capture.analysis_height

        try:
            while self._running:
                if self._stop_event and self._stop_event.is_set():
                    logger.info("[Pipeline] Interrupted by stop event.")
                    break
                    
                if self._pause_event and self._pause_event.is_set():
                    # Paused for screen lock / system suspend. The underlying loop
                    # isn't repainting, but notification flashes must still fire
                    # (this is exactly when the user misses notifications). Pull
                    # only flash commands; defer the rest until resume.
                    nfl = bool(self._cfg.notifications.flash_when_locked)
                    self._drain_flash_commands(enqueue=nfl)
                    flashing = self._service_idle_flash(time.monotonic()) if nfl else False
                    time.sleep(0.02 if flashing else 0.1)
                    continue

                if self._command_queue is not None:
                    import queue
                    while True:
                        try:
                            cmd = self._command_queue.get_nowait()
                        except queue.Empty:
                            break
                        self._handle_command(cmd)

                # --- Powered off: idle without driving the strip ---
                if not self._power:
                    self._set_capture_active(False)   # free the capture device
                    self._last_zone_colors = []
                    # Still flash for notifications when configured (wakes the
                    # strip for the blink, then powers it back off).
                    flashing = (
                        self._service_idle_flash(time.monotonic())
                        if self._cfg.notifications.flash_when_locked else False
                    )
                    if self._metrics_queue is not None:
                        import queue
                        try:
                            self._metrics_queue.put_nowait({
                                "fps": 0.0, "latency_ms": 0.0,
                                "uptime_s": time.monotonic() - (self._start_time or time.monotonic()),
                                "mode": "off", "power": False,
                                "color": [0, 0, 0], "zones": [],
                                "devices": len(self._channels),
                                "devices_connected": sum(1 for ch in self._channels if ch.led.is_connected),
                            })
                        except queue.Full:
                            pass
                    time.sleep(0.02 if flashing else 0.1)
                    continue

                # --- Effect schedule (checked at most every 5 s) ---
                if self._scheduler is not None and (time.monotonic() - self._last_sched_check) > 5.0:
                    self._last_sched_check = time.monotonic()
                    self._apply_schedule()

                # --- HDR state refresh (checked at most every 5 s) ---
                # Cheap DISPLAYCONFIG query; polled rather than per-frame so
                # toggling Windows HDR (or swapping displays) is picked up without
                # cross-process event plumbing.
                if self._hdr is not None and (time.monotonic() - self._last_hdr_check) > 5.0:
                    self._last_hdr_check = time.monotonic()
                    self._hdr.refresh()

                # Capture is only needed while screen-syncing; release it for
                # effect modes (self-correcting, also covers scheduler changes).
                self._set_capture_active(self._effects.current_mode == "screen_sync")

                t0 = time.monotonic()
                r, g, b = (0, 0, 0)
                # Capture health for this iteration. Effect modes don't capture,
                # so they're trivially "ok"; screen-sync sets this from the grab.
                capture_ok = True
                capture_reason = "ok"   # ok | no_frames | black | drm_suspected
                capture_backend = next(
                    (cap.active_backend for cap in self._captures.values()), None
                )
                # MSS on Windows renders fullscreen games / overlay video black —
                # flag it so the UI can advise installing WGC (see capture.py).
                degraded = capture_backend == "mss" and sys.platform == "win32"

                # Notification flash overlay: on an "on" segment it overrides the
                # strip with the flash colour; on "off"/inactive the real content
                # shows. The underlying loop still computes colours for metrics.
                flash_dir = self._flash_step(t0, paused=False)
                flash_rgb = flash_dir[1] if flash_dir[0] == "on" else None

                # --- Effect Processing (applies to every device) ---
                if self._effects.current_mode != "screen_sync":
                    color = self._effects.update()
                    if color:
                        r, g, b = color
                    if color is not None or flash_rgb is not None:
                        out = flash_rgb if flash_rgb is not None else (r, g, b)
                        for ch in self._channels:
                            ch.led.set_rgb(*out)
                            if color is not None:
                                ch.last_output_rgb = (int(r), int(g), int(b))
                    sent = True
                    time.sleep(1.0 / max(self._cfg.capture.fps_target, 1))
                else:
                    # --- Capture each distinct monitor once, share among devices ---
                    small_by_mon: dict[int, Optional[np.ndarray]] = {}
                    for mi, cap in self._captures.items():
                        frame = cap.grab()
                        small = self._gpu.resize(frame, w, h) if frame is not None else None  # type: ignore[union-attr]
                        # Tone-map washed HDR frames back to SDR before analysis.
                        # HDR state is keyed by the live display index, so map the
                        # capture's config key to the index the backend opened.
                        if small is not None and self._should_tonemap(self._resolved_index.get(mi, mi)):
                            hcfg = self._cfg.capture.hdr
                            small = tonemap_bgr(
                                small, hcfg.exposure, hcfg.contrast, hcfg.saturation_recovery,
                            )
                        small_by_mon[mi] = small

                    if not any(v is not None for v in small_by_mon.values()):
                        # Every monitor returned nothing this round — capture is
                        # producing no frames (a bad monitor_index, all backends
                        # exhausted, etc.). Surface it as a degraded snapshot so
                        # the UI shows "running but not syncing" instead of a
                        # frozen strip masquerading as healthy.
                        self._consecutive_black = 0
                        if self._metrics_queue is not None:
                            import queue
                            try:
                                self._metrics_queue.put_nowait({
                                    "fps": 0.0, "latency_ms": 0.0,
                                    "uptime_s": time.monotonic() - (self._start_time or time.monotonic()),
                                    "mode": self._effects.current_mode, "power": self._power,
                                    "color": [int(r), int(g), int(b)], "zones": self._last_zone_colors,
                                    "devices": len(self._channels),
                                    "devices_connected": sum(1 for ch in self._channels if ch.led.is_connected),
                                    "capture_ok": False, "capture_backend": capture_backend,
                                    "capture_reason": "no_frames", "degraded": degraded,
                                })
                            except queue.Full:
                                pass
                        time.sleep(0.01)
                        continue

                    # Capture IS delivering frames — but an exclusive-fullscreen
                    # game on the MSS backend (and DRM content on any backend)
                    # yields a valid *all-black* frame, not None, so it slips past
                    # the no-frames check above and the strip silently goes dark.
                    # Track sustained black so we can report the cause.
                    present = [v for v in small_by_mon.values() if v is not None]
                    if present and all(is_black_frame(v) for v in present):
                        self._consecutive_black += 1
                    else:
                        self._consecutive_black = 0

                    # --- Per-device analysis + output ---
                    for ch in self._channels:
                        small = small_by_mon.get(ch.monitor_index)
                        if small is None:
                            continue
                        # Transient-black debounce: a lone black frame from the
                        # capture backend (common on WGC/DXGI even when the screen
                        # is static) would blink the strip off. Hold the last
                        # colour until black persists past the debounce window, so
                        # a glitch frame is ignored but a real black-out still
                        # turns the strip dark. A flash overrides regardless.
                        if flash_rgb is None and self._hold_transient_black(ch, small):
                            r, g, b = self._last_output_rgb
                            continue
                        zone_regions = ch.zones.extract_regions(small)
                        zone_colors = ch.analyzer.analyze_zones(zone_regions)
                        smoothed_zones = ch.smoother.smooth_zones(zone_colors)
                        ch.last_zone_colors = [
                            (int(c[0]), int(c[1]), int(c[2])) for (_zone, c) in smoothed_zones
                        ]
                        combined = ch.analyzer.combine_zone_colors(smoothed_zones)
                        r, g, b = ch.smoother.smooth_combined(combined)
                        # Remember this channel's real colour so a flash that
                        # finishes while locked restores the right per-strip frame.
                        ch.last_output_rgb = (int(r), int(g), int(b))
                        if flash_rgb is not None:
                            fr, fg, fb = flash_rgb
                            if ch.led.is_addressable:
                                ch.led.set_pixels([(fr, fg, fb)] * ch.led_count)
                            else:
                                ch.led.set_rgb(fr, fg, fb)
                        elif ch.led.is_addressable and self._cfg.gradient.enabled:
                            pixels = generate_gradient(
                                self._cfg.gradient.mode, ch.last_zone_colors,
                                ch.led_count, self._cfg.gradient.gamma,
                            )
                            ch.led.set_pixels(pixels)
                        else:
                            ch.led.set_rgb(r, g, b)
                    sent = True
                    # Capture delivered at least one usable frame this round.
                    capture_ok = any(cap.is_healthy for cap in self._captures.values())
                    # ...but if every delivered frame has been black for a
                    # sustained run, capture is effectively dead even though the
                    # backend reports healthy. Flag it with a cause.
                    black_ok, black_reason = _nosignal_verdict(self._consecutive_black, capture_backend)
                    if not black_ok:
                        capture_ok = False
                        capture_reason = black_reason
                    # Live preview reflects the first channel.
                    self._last_zone_colors = self._channels[0].last_zone_colors if self._channels else []

                # Remember the last real colour so a flash that fires while the
                # strip is later locked/paused can restore the frozen frame.
                self._last_output_rgb = (int(r), int(g), int(b))

                # --- Metrics ---
                latency_ms = (time.monotonic() - t0) * 1000.0
                fps = 1000.0 / latency_ms if latency_ms > 0 else 0
                connected = sum(1 for ch in self._channels if ch.led.is_connected)

                metrics = {
                    "fps": fps,
                    "latency_ms": latency_ms,
                    "capture_time_ms": latency_ms * 0.4,
                    "process_time_ms": latency_ms * 0.4,
                    "led_transmit_ms": latency_ms * 0.2,
                    "uptime_s": time.monotonic() - (self._start_time or time.monotonic()),
                    "mode": self._effects.current_mode if self._power else "off",
                    "power": self._power,
                    "color": [int(r), int(g), int(b)],
                    "zones": self._last_zone_colors,  # per-zone RGB for live preview
                    "devices": len(self._channels),
                    "devices_connected": connected,
                    "capture_ok": capture_ok,
                    "capture_backend": capture_backend,
                    "capture_reason": capture_reason,
                    "degraded": degraded,
                    # True when any captured monitor currently has HDR enabled —
                    # lets the UI badge "HDR" and confirm tone-mapping is active.
                    "hdr_active": bool(
                        self._hdr is not None
                        and any(
                            self._hdr.is_hdr(self._resolved_index.get(mi, mi))
                            for mi in self._captures
                        )
                    ),
                }

                if self._metrics is not None:
                    self._metrics.record_frame(latency_ms)
                    
                if self._metrics_queue is not None:
                    import queue
                    try:
                        self._metrics_queue.put_nowait(metrics)
                    except queue.Full:
                        pass

                # Throttle the per-frame debug line to ≤ 1 / 2 s so DEBUG mode
                # doesn't churn the rotating log at the capture frame rate.
                if logger.isEnabledFor(logging.DEBUG):
                    now_dbg = time.monotonic()
                    if now_dbg - self._last_debug_log >= 2.0:
                        self._last_debug_log = now_dbg
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
    # Command handling
    # ------------------------------------------------------------------

    def _handle_command(self, cmd: dict) -> None:
        """Apply a single command pulled from the controller's command queue."""
        action = cmd.get("action")
        if action == "reload":
            self._cfg = cmd["config"]
            self._apply_config_hot()
        elif action == "flash":
            self._enqueue_flash(cmd.get("color"), cmd.get("pattern") or {})
        elif action == "set_mode":
            mode = cmd.get("mode")
            params = cmd.get("params", {})
            if mode == "off":
                # Power the strip off completely and stop any effect.
                self._effects.set_mode("screen_sync")
                for ch in self._channels:
                    ch.led.turn_off()
                self._power = False
                self._mode = "off"
                logger.info("[Pipeline] Powered off.")
            else:
                # Check each strip's power and turn it on if off,
                # before applying the mode (FR-POWER).
                for ch in self._channels:
                    ch.led.ensure_on()
                self._power = True
                self._effects.set_mode(mode, params)
                self._mode = mode
                logger.info("[Pipeline] Mode switched to %s", mode)

    def _drain_flash_commands(self, enqueue: bool = True) -> None:
        """While paused, pull pending commands acting only on ``flash`` ones;
        non-flash commands are re-queued so they survive until resume.

        When *enqueue* is False the flash is dropped (used when
        ``flash_when_locked`` is disabled) so stale flashes don't fire on unlock.
        """
        if self._command_queue is None:
            return
        import queue
        deferred = []
        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                break
            if cmd.get("action") == "flash":
                if enqueue:
                    self._enqueue_flash(cmd.get("color"), cmd.get("pattern") or {})
            else:
                deferred.append(cmd)
        for cmd in deferred:
            try:
                self._command_queue.put_nowait(cmd)
            except queue.Full:
                pass

    def _hold_transient_black(self, ch: "_Channel", frame) -> bool:
        """Update *ch*'s black streak and report whether this black frame should
        be held (skipped) as a transient capture glitch.

        Returns True only while a black run is within the debounce window, so a
        lone spurious black frame is ignored (strip holds its colour) but a
        sustained black-out (streak past the window) falls through to be sent.
        Non-black frames reset the streak.
        """
        if is_black_frame(frame):
            ch.black_streak += 1
            return ch.black_streak <= _BLACK_DEBOUNCE_FRAMES
        ch.black_streak = 0
        return False

    # ------------------------------------------------------------------
    # Notification flash overlay
    # ------------------------------------------------------------------

    def _enqueue_flash(self, color, pattern: dict) -> None:
        """Build a blink schedule from *color* + *pattern* and queue it.

        *pattern* may carry ``blink_count``, ``on_ms``, ``off_ms`` and
        ``brightness``; missing values fall back to sensible defaults.
        """
        if not color:
            return
        try:
            rgb = [max(0, min(255, int(c))) for c in color][:3]
            if len(rgb) != 3:
                return
        except (TypeError, ValueError):
            return
        try:
            bright = max(0.0, min(1.0, float(pattern.get("brightness", 1.0))))
        except (TypeError, ValueError):
            bright = 1.0
        r, g, b = (int(c * bright) for c in rgb)
        try:
            blink_count = max(1, int(pattern.get("blink_count", 2)))
            on_ms = max(20, int(pattern.get("on_ms", 180)))
            off_ms = max(0, int(pattern.get("off_ms", 120)))
        except (TypeError, ValueError):
            blink_count, on_ms, off_ms = 2, 180, 120

        segments = []
        for i in range(blink_count):
            segments.append({"on": True, "rgb": (r, g, b), "dur": on_ms / 1000.0})
            if i < blink_count - 1 and off_ms > 0:
                segments.append({"on": False, "rgb": (0, 0, 0), "dur": off_ms / 1000.0})
        self._flash_queue.append({"segments": segments})

    def _flash_step(self, now: float, paused: bool):
        """Advance the flash state machine. Returns a directive tuple:
        ``("inactive",)``, ``("on", (r,g,b))`` or ``("off",)``.

        Side effects only at transitions: ``ensure_on`` on start, and on finish
        either power the strip back off (if it was nominally off) or restore the
        last frame (if it was a paused/locked flash). Painting of segments is
        left to the caller so the active loop and the idle loop can share this.
        """
        if self._flash_active is None:
            if not self._flash_queue:
                return ("inactive",)
            fa = self._flash_queue.popleft()
            fa["i"] = 0
            fa["seg_end"] = now + fa["segments"][0]["dur"]
            for ch in self._channels:
                try:
                    ch.led.ensure_on()
                except Exception:  # pragma: no cover - device hiccup
                    pass
            self._flash_active = fa

        fa = self._flash_active
        while now >= fa["seg_end"]:
            fa["i"] += 1
            if fa["i"] >= len(fa["segments"]):
                self._finish_flash(paused)
                return ("inactive",)
            fa["seg_end"] = now + fa["segments"][fa["i"]]["dur"]

        seg = fa["segments"][fa["i"]]
        return ("on", seg["rgb"]) if seg["on"] else ("off",)

    def _finish_flash(self, paused: bool) -> None:
        """Terminal restore for a completed flash.

        The restore decision is taken from the *current* power/pause state, not
        the state captured when the flash started — so a flash that began while
        active but completes after the app was paused (screen lock mid-flash)
        still restores instead of leaving the flash colour stuck on.
        """
        self._flash_active = None
        try:
            if not self._power:
                for ch in self._channels:
                    ch.led.set_rgb(0, 0, 0)
                    ch.led.turn_off()
            elif paused:
                self._restore_output()
            # Active + powered: the normal loop repaints next tick, nothing to do.
        except Exception:  # pragma: no cover - device hiccup
            pass

    def _restore_output(self) -> None:
        """Repaint each channel's own last real colour (used after a paused/locked
        flash, where the normal loop isn't repainting). Per-channel so multi-device
        setups don't all collapse to a single colour."""
        for ch in self._channels:
            r, g, b = getattr(ch, "last_output_rgb", (0, 0, 0))
            try:
                if ch.led.is_addressable:
                    ch.led.set_pixels([(r, g, b)] * ch.led_count)
                else:
                    ch.led.set_rgb(r, g, b)
            except Exception:  # pragma: no cover - device hiccup
                pass

    def _service_idle_flash(self, now: float) -> bool:
        """Drive the flash overlay while the strip isn't being repainted (paused
        for lock/suspend, or powered off). Paints on/off segments directly and
        returns True while a flash is in progress (so the caller tightens its
        sleep cadence for a crisp blink)."""
        directive = self._flash_step(now, paused=True)
        if directive[0] == "on":
            fr, fg, fb = directive[1]
            for ch in self._channels:
                try:
                    if ch.led.is_addressable:
                        ch.led.set_pixels([(fr, fg, fb)] * ch.led_count)
                    else:
                        ch.led.set_rgb(fr, fg, fb)
                except Exception:  # pragma: no cover - device hiccup
                    pass
            return True
        if directive[0] == "off":
            for ch in self._channels:
                try:
                    if ch.led.is_addressable:
                        ch.led.set_pixels([(0, 0, 0)] * ch.led_count)
                    else:
                        ch.led.set_rgb(0, 0, 0)
                except Exception:  # pragma: no cover - device hiccup
                    pass
            return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_tonemap(self, monitor_index: int) -> bool:
        """Whether to HDR→SDR tone-map *monitor_index* this frame.

        ``off`` never, ``on`` always, ``auto`` only when the display reports HDR.
        """
        hcfg = self._cfg.capture.hdr
        mode = getattr(hcfg, "mode", "auto")
        if mode == "off":
            return False
        if mode == "on":
            return True
        return self._hdr is not None and self._hdr.is_hdr(monitor_index)

    def _apply_schedule(self) -> None:
        """Activate/deactivate scheduled effects for the current time (FR-EFF-08)."""
        entry = self._scheduler.current() if self._scheduler else None
        if entry:
            if not self._scheduled_active or self._effects.current_mode != entry.get("effect"):
                self._effects.set_mode(entry.get("effect", "screen_sync"), entry.get("params", {}))
                self._scheduled_active = True
                logger.info("[Pipeline] Schedule activated effect '%s'.", entry.get("effect"))
        elif self._scheduled_active:
            # Window ended — return to screen sync.
            self._effects.set_mode("screen_sync")
            self._scheduled_active = False
            logger.info("[Pipeline] Schedule window ended; back to screen_sync.")

    def _apply_config_hot(self) -> None:
        """Apply config changes without a process restart.

        If the device/monitor *topology* changed, rebuild captures + channels;
        otherwise update each channel's analysis settings in place.
        """
        if self._topology_sig() != self._topology:
            logger.info("[Pipeline] Device/monitor topology changed; rebuilding I/O.")
            self._teardown_io()
            self._build_io()
            return

        z = self._cfg.zones
        c = self._cfg.color
        s = self._cfg.smoothing
        for ch in self._channels:
            ch.zones = ZoneManager(z.top, z.bottom, z.left, z.right, edge_fraction=z.edge_fraction)
            ch.analyzer = ColorAnalyzer(
                mode=c.mode,
                black_threshold=c.ignore_black_threshold,
                white_threshold=c.ignore_white_threshold,
                kmeans_clusters=c.kmeans_clusters,
                saturation_weight_power=c.saturation_weight_power,
                min_saturation=c.min_saturation,
                vibrance=getattr(c, "vibrance", 1.0),
            )
            ch.smoother = SmoothingEngine(
                enabled=s.enabled,
                base_alpha=s.base_alpha,
                fast_alpha=s.adaptive_fast_alpha,
                fast_threshold=s.adaptive_fast_threshold,
                min_change=s.min_change,
            )
        # Re-apply the active effect with its (possibly edited) params so changes
        # to speed/colour/custom-sequence take effect live without a mode switch.
        mode = self._effects.current_mode
        if self._power and mode != "screen_sync":
            params = (getattr(self._cfg.effects, "params", {}) or {}).get(mode, {})
            try:
                self._effects.set_mode(mode, params)
            except Exception as exc:
                logger.debug("[Pipeline] effect re-apply failed: %s", exc)
        logger.info("[Pipeline] Hot-reloaded configuration (%d channel(s)).", len(self._channels))

    # ------------------------------------------------------------------
    # Multi-device I/O construction
    # ------------------------------------------------------------------

    def _topology_sig(self) -> tuple:
        """Signature of the device/monitor layout; changes trigger a rebuild.

        Includes ``protocol`` and ``port`` because they determine *which* driver
        is instantiated (and where it connects). Identity is protocol-aware:
        MagicHome is keyed by ``mac or ip`` (MAC-stable across DHCP changes), but
        WLED has no MAC-based rediscovery, so it is keyed by ``ip`` — otherwise
        changing a WLED device's IP while a MAC is set would not rebuild.
        """
        def _identity(s: dict) -> str:
            if s["protocol"] == "magichome":
                return str(s["mac"] or s["ip"])
            return str(s["ip"])

        return tuple(sorted(
            (s["protocol"], _identity(s), s["port"], s["monitor_index"], s["led_count"])
            for s in _device_specs(self._cfg)
        ))

    def _build_io(self) -> None:
        """Create one capture per distinct monitor and one channel per device."""
        from .discovery import classify_device
        cfg = self._cfg
        specs = _device_specs(cfg)
        z, c, s = cfg.zones, cfg.color, cfg.smoothing
        min_interval = 1.0 / max(cfg.capture.fps_target, 1)

        # Captures are acquired lazily — only while actually screen-syncing
        # (see _set_capture_active). Start empty.
        self._captures = {}

        # One channel per device.
        self._channels = []
        for sp in specs:
            protocol = sp.get("protocol", "magichome")
            # MagicHome's MAC-aware discovery recovers a controller after a DHCP
            # IP change; it doesn't apply to other protocols, which use the
            # configured IP directly (WLED is always per-pixel addressable).
            if protocol == "magichome":
                info = self._discover_spec(sp)
                ip = info.ip if info else sp["ip"]
                kind = classify_device(info) if info else "single"
            else:
                ip = sp["ip"]
                kind = "addressable"
            led = create_driver({
                **sp, "ip": ip, "kind": kind, "min_update_interval": min_interval,
            })
            if led.connect():
                led.turn_on()
            else:
                logger.warning("[Pipeline] Could not connect to %s; will retry.", ip)
            self._channels.append(_Channel(
                name=sp["name"], monitor_index=sp["monitor_index"], led=led,
                zones=ZoneManager(z.top, z.bottom, z.left, z.right, edge_fraction=z.edge_fraction),
                analyzer=ColorAnalyzer(
                    mode=c.mode, black_threshold=c.ignore_black_threshold,
                    white_threshold=c.ignore_white_threshold, kmeans_clusters=c.kmeans_clusters,
                    saturation_weight_power=c.saturation_weight_power, min_saturation=c.min_saturation,
                    vibrance=getattr(c, "vibrance", 1.0),
                ),
                smoother=SmoothingEngine(
                    enabled=s.enabled, base_alpha=s.base_alpha, fast_alpha=s.adaptive_fast_alpha,
                    fast_threshold=s.adaptive_fast_threshold, min_change=s.min_change,
                ),
                # Use the driver's live LED count (WLED refines it from /json/info
                # on connect; MagicHome keeps the configured value) so the
                # gradient is sized to the real strip, and the run loop can read
                # ch.led_count without depending on a driver-specific attribute.
                led_count=getattr(led, "led_count", sp["led_count"]),
            ))

        self._topology = self._topology_sig()
        logger.info("[Pipeline] Built %d device channel(s).", len(self._channels))
        # Acquire capture now only if we're in screen-sync and powered.
        self._set_capture_active(self._power and self._effects.current_mode == "screen_sync")

    def _acquire_captures(self) -> None:
        """Open one ScreenCaptureManager per distinct monitor (idempotent).

        Each requested monitor is resolved to a *stable identity target* (by
        ``monitor_id`` when set, else by index) so the capture backends re-find
        the same physical display via ``gdi_name``/position rather than a bare
        index — the fix for hybrid-GPU setups where an index points each backend
        at a different monitor (or none).
        """
        if self._captures:
            return
        cfg = self._cfg
        specs = _device_specs(cfg)

        try:
            from .monitors import list_monitors, resolve_monitor
            mons = list_monitors()
        except Exception:
            mons, resolve_monitor = [], None
        monitor_count = len(mons)

        # monitor_index -> first non-empty monitor_id in that group, so a group
        # keyed by index still resolves by its stable id when one is stored.
        id_by_index: dict[int, str] = {}
        for sp in specs:
            mi = sp["monitor_index"]
            if sp.get("monitor_id") and mi not in id_by_index:
                id_by_index[mi] = sp["monitor_id"]

        caps: dict[int, ScreenCaptureManager] = {}
        # raw (config) monitor index -> live index the backend actually opened.
        # HDR state is keyed by the live EnumDisplayMonitors index, so tone-map
        # and the hdr_active badge must look up by the resolved index, not the
        # config one (they differ after a reorder / hybrid-GPU remap).
        resolved_index: dict[int, int] = {}
        # Key each capture by the *requested* monitor index so the channel lookup
        # in the grab loop (small_by_mon.get(ch.monitor_index)) still resolves;
        # the backend opens the *resolved target* so it grabs the right display.
        try:
            for raw_mi in sorted({sp["monitor_index"] for sp in specs}):
                stored = {"id": id_by_index.get(raw_mi, ""), "index": raw_mi}
                target = resolve_monitor(stored, mons) if (mons and resolve_monitor) else None
                if target is None:
                    # No identity/index match — clamp to a real display (legacy
                    # behaviour) so a stale index doesn't freeze the LEDs.
                    mi = raw_mi
                    if monitor_count > 0 and mi > monitor_count - 1:
                        logger.warning(
                            "[Pipeline] monitor_index %d is out of range (%d display(s) "
                            "detected); falling back to monitor 0.", raw_mi, monitor_count,
                        )
                        mi = 0
                    target = mons[mi] if (mons and mi < monitor_count) else {"index": mi}
                elif target.get("index") != raw_mi:
                    logger.info(
                        "[Pipeline] monitor %r resolved to index %d (config index was %d) "
                        "via stable identity.", stored["id"] or "(by index)", target["index"], raw_mi,
                    )
                # Pin capture.monitor_id on first run so the selection survives a
                # later display reorder (best-effort; only the global capture target).
                if raw_mi == cfg.capture.monitor_index and target.get("id"):
                    self._backfill_capture_id(target["id"])
                cap = ScreenCaptureManager(
                    preferred_method=cfg.capture.method, target=target, fps_target=cfg.capture.fps_target,
                    analysis_width=cfg.capture.analysis_width, analysis_height=cfg.capture.analysis_height,
                )
                cap.start()  # raises if no backend can be opened
                caps[raw_mi] = cap
                resolved_index[raw_mi] = int(target.get("index", raw_mi))
        except Exception:
            # A later cap.start() failed: stop the managers already started so
            # their OS duplication/CPU resources don't leak (self._captures is
            # still empty, so the normal release path can't reach them).
            for started in caps.values():
                try:
                    started.stop()
                except Exception:
                    pass
            raise
        self._captures = caps
        self._resolved_index = resolved_index
        logger.info("[Pipeline] Capture acquired (%d monitor(s)).", len(caps))

    def _backfill_capture_id(self, resolved_id: str) -> None:
        """Persist ``capture.monitor_id`` once if it was unset, migrating an
        index-only config to a stable identity. Best-effort and event-free (uses
        ``ConfigManager.save`` directly), so it never triggers a restart."""
        try:
            from .config import ConfigManager
            if (
                resolved_id
                and not self._cfg.capture.monitor_id
                and self._cfg is ConfigManager.get()
            ):
                # save() serialises the in-memory instance, so set the field then
                # confirm the write reached disk. If it didn't, clear the pin so a
                # later run retries instead of treating it as already persisted.
                self._cfg.capture.monitor_id = resolved_id
                if ConfigManager.save():
                    logger.info(
                        "[Pipeline] Pinned capture.monitor_id=%s (migrated from index %d).",
                        resolved_id, self._cfg.capture.monitor_index,
                    )
                else:
                    self._cfg.capture.monitor_id = ""
        except Exception as exc:  # pragma: no cover - persistence edge cases
            logger.debug("[Pipeline] monitor_id backfill skipped: %s", exc)

    def _release_captures(self) -> None:
        """Stop + release all capture devices (frees the OS duplication + CPU)."""
        if not self._captures:
            return
        for cap in self._captures.values():
            try:
                cap.stop()
            except Exception:
                pass
        self._captures = {}
        self._resolved_index = {}
        logger.info("[Pipeline] Capture released (effect/off mode).")

    def _set_capture_active(self, active: bool) -> None:
        """Acquire capture when screen-syncing, release it otherwise."""
        if active:
            self._acquire_captures()
        else:
            self._release_captures()

    def _teardown_io(self) -> None:
        """Turn off + release all LED controllers and capture managers."""
        for ch in self._channels:
            try:
                ch.led.set_rgb(0, 0, 0)
                ch.led.turn_off()
                ch.led.disconnect()
            except Exception:
                pass
        self._channels = []
        for cap in self._captures.values():
            try:
                cap.stop()
            except Exception:
                pass
        self._captures = {}

    def _discover_spec(self, spec: dict) -> Optional[DeviceInfo]:
        """Resolve a device spec to a reachable controller (MAC-aware)."""
        try:
            discovery = DeviceDiscovery(
                preferred_ip=spec["ip"], preferred_mac=spec["mac"], subnet=spec["subnet"],
                connect_timeout=spec["connect_timeout"], discovery_timeout=spec["discovery_timeout"],
                cache_file=spec["cache_file"],
            )
            return discovery.find_device()
        except Exception as exc:
            logger.warning("[Pipeline] Discovery error for %s: %s", spec.get("ip"), exc)
            return None

    def _shutdown(self) -> None:
        """Gracefully release all resources."""
        logger.info("[Pipeline] Shutting down …")
        self._teardown_io()
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
