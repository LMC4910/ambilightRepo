"""
Logging Module
==============
Configures the application-wide logging pipeline with:

* Rotating file handler with configurable size cap and backup count.
* Coloured console output (falls back gracefully on Windows without colorama).
* A lightweight FPS / performance metrics subsystem that emits statistics
  at a configurable cadence without blocking the hot path.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# ANSI colour helpers (no mandatory external deps)
# ---------------------------------------------------------------------------

_COLOURS: dict[int, str] = {
    logging.DEBUG: "\033[36m",      # cyan
    logging.INFO: "\033[32m",       # green
    logging.WARNING: "\033[33m",    # yellow
    logging.ERROR: "\033[31m",      # red
    logging.CRITICAL: "\033[35m",   # magenta
}
_RESET = "\033[0m"

_COLOUR_SUPPORT: bool = (
    sys.stdout.isatty()
    or os.environ.get("FORCE_COLOR", "").lower() in ("1", "true", "yes")
)


class _ColouredFormatter(logging.Formatter):
    """Formatter that prefixes level name with an ANSI colour escape."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        if _COLOUR_SUPPORT:
            colour = _COLOURS.get(record.levelno, "")
            return f"{colour}{formatted}{_RESET}"
        return formatted


# ---------------------------------------------------------------------------
# FPS / performance metrics tracker
# ---------------------------------------------------------------------------

class PerformanceMetrics:
    """
    Thread-safe frame-rate and latency tracker.

    Call :meth:`record_frame` on every processed frame.  A background daemon
    thread emits statistics to *logger* every *interval* seconds.

    Attributes
    ----------
    avg_fps:
        Rolling average frames per second over the last *window* frames.
    avg_latency_ms:
        Rolling average end-to-end latency in milliseconds.
    """

    def __init__(
        self,
        logger: logging.Logger,
        interval: float = 5.0,
        window: int = 150,
    ) -> None:
        self._logger = logger
        self._interval = interval
        self._window = window
        self._timestamps: deque[float] = deque(maxlen=window)
        self._latencies: deque[float] = deque(maxlen=window)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def avg_fps(self) -> float:
        with self._lock:
            if len(self._timestamps) < 2:
                return 0.0
            elapsed = self._timestamps[-1] - self._timestamps[0]
            return (len(self._timestamps) - 1) / elapsed if elapsed > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        with self._lock:
            if not self._latencies:
                return 0.0
            return sum(self._latencies) / len(self._latencies)

    def record_frame(self, latency_ms: float = 0.0) -> None:
        """Record that one frame was processed with the given *latency_ms*."""
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)
            if latency_ms > 0:
                self._latencies.append(latency_ms)

    def start(self) -> None:
        """Start the background statistics reporter."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._report_loop,
            name="perf-metrics",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background statistics reporter."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _report_loop(self) -> None:
        while self._running:
            time.sleep(self._interval)
            fps = self.avg_fps
            lat = self.avg_latency_ms
            self._logger.info(
                "[Metrics] FPS=%.1f | Avg latency=%.1f ms", fps, lat
            )


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/ambilight.log",
    max_bytes: int = 20_971_520,
    backup_count: int = 10,
    show_fps: bool = True,
    fps_interval: float = 5.0,
    file_level: str = "INFO",
) -> PerformanceMetrics:
    """
    Configure root logging and return a :class:`PerformanceMetrics` instance.

    Parameters
    ----------
    level:
        Console / root log level string, e.g. ``"DEBUG"``, ``"INFO"``.
    log_file:
        Destination for the rotating log file.  Parent directories are created
        automatically.
    max_bytes:
        Maximum size of each log file before rotation.
    backup_count:
        Number of rotated backups to retain (total on-disk cap ≈
        ``max_bytes × (backup_count + 1)``).
    show_fps:
        Whether to start the FPS reporting background thread.
    fps_interval:
        Seconds between FPS / latency log lines.
    file_level:
        On-disk log level, independent of ``level``.  Defaults to ``INFO`` so that
        running with a DEBUG *console* never floods/churns the rotating file.

    Returns
    -------
    PerformanceMetrics
        A started metrics object; the caller can call ``record_frame()`` on it.
    """
    numeric_console = getattr(logging, level.upper(), logging.INFO)
    numeric_file = getattr(logging, file_level.upper(), logging.INFO)

    root = logging.getLogger()
    # Root must pass the most verbose of the two so each handler can filter its own.
    root.setLevel(min(numeric_console, numeric_file))

    # Remove any handlers added by previous calls (e.g. during tests)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    # Console handler — uses the (possibly verbose) console level.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_console)
    console_handler.setFormatter(
        _ColouredFormatter(fmt=fmt, datefmt=date_fmt)
    )
    root.addHandler(console_handler)

    # Rotating file handler — bounded by size, and kept at file_level so DEBUG
    # console output does not bloat the on-disk log.
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_file)
    file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=date_fmt))
    root.addHandler(file_handler)

    perf_logger = logging.getLogger("ambilight.perf")
    metrics = PerformanceMetrics(
        logger=perf_logger,
        interval=fps_interval,
    )
    if show_fps:
        metrics.start()

    logging.getLogger(__name__).info(
        "Logging initialised — console=%s, file=%s (%s), cap=%d×%dB",
        level, file_level, log_path, backup_count + 1, max_bytes,
    )
    return metrics
