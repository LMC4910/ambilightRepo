"""
Pipeline Controller Module
==========================
Manages the `AmbilightPipeline` in an isolated `multiprocessing.Process`.
Listens to `EventBus` to pause/resume the pipeline on OS events.
Relays metrics from the pipeline process back to the EventBus.
Supervises the worker process and restarts it automatically if it crashes
(FR-SVC-03: recovery within 10 seconds).
"""

import asyncio
import logging
import multiprocessing
import queue
import time
from typing import Optional

from .events import bus
from .pipeline import AmbilightPipeline
from .config import AppConfig, ConfigManager

logger = logging.getLogger(__name__)

# How often the watchdog checks worker liveness, and how long to wait before
# relaunching a crashed worker (must satisfy the ≤10 s recovery requirement).
_WATCHDOG_INTERVAL = 2.0
_RESTART_DELAY = 1.0


def _pipeline_worker(config: Optional[AppConfig], stop_event: multiprocessing.Event, pause_event: multiprocessing.Event, metrics_queue: multiprocessing.Queue, command_queue: multiprocessing.Queue) -> None:
    """Entry point for the isolated pipeline process."""
    try:
        # On spawn-based platforms (Windows) the child does not inherit the
        # ConfigManager singleton, so seed it from the passed config.
        if config is not None:
            ConfigManager._instance = config
        pipeline = AmbilightPipeline(config=config, stop_event=stop_event, pause_event=pause_event, metrics_queue=metrics_queue, command_queue=command_queue)
        pipeline.start()
        pipeline.run()
    except Exception as exc:
        logger.exception("[PipelineWorker] Unrecoverable error: %s", exc)


class PipelineController:
    """Orchestrates the AmbilightPipeline process from the main asyncio loop."""

    def __init__(self) -> None:
        self._process: Optional[multiprocessing.Process] = None
        self._stop_event = multiprocessing.Event()
        self._pause_event = multiprocessing.Event()
        self._metrics_queue = multiprocessing.Queue()
        self._command_queue = multiprocessing.Queue()
        self._metrics_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        # True while the pipeline is *meant* to be running; lets the watchdog
        # distinguish an intentional stop from a crash.
        self._should_run = False
        self._restart_count = 0

    async def setup(self) -> None:
        """Subscribe to OS events."""
        await bus.subscribe("DISPLAY_OFF", self._on_display_off)
        await bus.subscribe("SYSTEM_SUSPEND", self._on_display_off)
        await bus.subscribe("DISPLAY_ON", self._on_display_on)
        await bus.subscribe("SYSTEM_RESUME", self._on_display_on)
        await bus.subscribe("DISPLAY_CHANGED", self._on_display_changed)
        await bus.subscribe("CONFIG_UPDATE", self._on_config_update)

    def _spawn(self) -> None:
        """Launch a fresh worker process. Caller manages _should_run."""
        self._stop_event.clear()
        self._pause_event.clear()

        # Read config at launch time (after ConfigManager.load in service boot)
        # and pass it explicitly so spawn-based child processes use it.
        try:
            cfg = ConfigManager.get()
        except Exception:
            cfg = None

        self._process = multiprocessing.Process(
            target=_pipeline_worker,
            args=(cfg, self._stop_event, self._pause_event, self._metrics_queue, self._command_queue),
            daemon=True,
            name="AmbilightCaptureProcess"
        )
        self._process.start()
        logger.info("[PipelineController] Started pipeline process (PID: %s)", self._process.pid)

    def start(self) -> None:
        """Launch the pipeline process and its supervisor tasks."""
        if self._process is not None and self._process.is_alive():
            return

        self._should_run = True
        self._spawn()

        # Start background task to drain metrics queue and publish to EventBus
        if self._metrics_task is None or self._metrics_task.done():
            self._metrics_task = asyncio.create_task(self._poll_metrics())
        # Start the crash watchdog
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog())

    def stop(self) -> None:
        """Signal the pipeline process to stop gracefully."""
        self._should_run = False
        self._stop_event.set()
        if self._process:
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                logger.warning("[PipelineController] Process did not exit cleanly; terminating.")
                self._process.terminate()
            self._process = None

        if self._metrics_task:
            self._metrics_task.cancel()
            self._metrics_task = None
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None

        logger.info("[PipelineController] Pipeline stopped.")

    def restart(self) -> None:
        """Stop and re-launch the pipeline process."""
        logger.info("[PipelineController] Restart requested.")
        self.stop()
        self.start()

    def pause(self) -> None:
        """Pause the capture loop without killing the process."""
        logger.info("[PipelineController] Pause requested.")
        self._pause_event.set()

    def resume(self) -> None:
        """Resume a paused capture loop."""
        logger.info("[PipelineController] Resume requested.")
        self._pause_event.clear()

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def status(self) -> dict:
        """Structured status snapshot for the /health and /status endpoints."""
        return {
            "running": self.is_alive,
            "paused": self.is_paused,
            "pid": self._process.pid if self._process else None,
            "restarts": self._restart_count,
        }

    async def _watchdog(self) -> None:
        """Relaunch the worker if it dies unexpectedly (FR-SVC-03)."""
        while True:
            try:
                await asyncio.sleep(_WATCHDOG_INTERVAL)
                if not self._should_run:
                    continue
                if self._process is not None and not self._process.is_alive():
                    self._restart_count += 1
                    logger.error(
                        "[PipelineController] Worker exited unexpectedly (code=%s). "
                        "Restarting (#%d) …",
                        self._process.exitcode, self._restart_count,
                    )
                    await asyncio.sleep(_RESTART_DELAY)
                    if self._should_run:
                        self._spawn()
                        await bus.publish("PIPELINE_RESTARTED", {"count": self._restart_count})
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[PipelineController] Watchdog error: %s", exc)

    async def _on_display_off(self, *args, **kwargs) -> None:
        logger.info("[PipelineController] Display off/suspended. Pausing pipeline.")
        self._pause_event.set()

    async def _on_display_on(self, *args, **kwargs) -> None:
        logger.info("[PipelineController] Display on/resumed. Resuming pipeline.")
        self._pause_event.clear()

    async def _on_display_changed(self, *args, **kwargs) -> None:
        """Monitor connect/disconnect: rebuild capture by restarting the worker.

        Re-enumerating monitors and re-opening the capture backend safely is
        simplest by relaunching the (cheap) worker process, which re-runs the
        full backend-selection chain in ``AmbilightPipeline.start()``.
        """
        if not self._should_run:
            return
        logger.info("[PipelineController] Display configuration changed. Rebuilding capture.")
        self.restart()

    async def _on_config_update(self, cfg: AppConfig) -> None:
        logger.info("[PipelineController] Config update received. Sending to pipeline.")
        self._command_queue.put({"action": "reload", "config": cfg})

    def set_mode(self, mode: str, params: dict) -> None:
        """Send mode change command to the pipeline process."""
        self._command_queue.put({
            "action": "set_mode",
            "mode": mode,
            "params": params
        })

    async def _poll_metrics(self) -> None:
        """Poll the metrics queue and emit them as 'METRICS_UPDATE' events."""
        loop = asyncio.get_running_loop()
        while True:
            try:
                # Use run_in_executor since queue.get is blocking
                metric = await loop.run_in_executor(None, self._metrics_queue.get, True, 0.1)
                await bus.publish("METRICS_UPDATE", metric)
            except queue.Empty:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[PipelineController] Metrics poll error: %s", exc)
                await asyncio.sleep(1)
