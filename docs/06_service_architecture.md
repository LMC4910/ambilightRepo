# Service Architecture Document
## Ambilight Python Service — Design and Operational Guide

**Version:** 1.0  

---

## 1. Service Responsibilities

The Python service is the **sole owner of all LED and capture logic**. It is not a helper process — it is the product. The Electron UI is a view into the service.

| Responsibility | Module |
|---|---|
| Screen capture + frame analysis | `capture.py`, `color.py`, `zones.py` |
| Colour smoothing | `smoothing.py` |
| Gradient generation | `service/gradient_engine.py` |
| LED device communication | `led_output.py` |
| Device discovery + reconnect | `discovery.py` |
| Effects scheduling | `service/effects_engine.py` |
| Profile management | `service/profile_manager.py` |
| Display event handling | `service/platform/*.py` |
| REST + WebSocket API | `service/api_server.py` |
| Configuration management | `config.py` + `service/config_api.py` |
| Logging + metrics | `logging_setup.py` |

---

## 2. Service Lifecycle

```
OS Boot / User Login
       │
       ▼
  Service Manager (NSSM / launchd / systemd)
       │ spawns
       ▼
  Python: ambilight.service.__main__
       │
       ├── 1. Read config from ~/.ambilight/config.yaml
       ├── 2. Generate auth_token → ~/.ambilight/auth_token
       ├── 3. Start FastAPI server (uvicorn) on :7825/:7826
       ├── 4. Start DisplayEventWatcher
       ├── 5. Start DeviceDiscovery → connect to LED controller
       ├── 6. Start CaptureProcess (subprocess for isolation)
       └── 7. Start PerformanceMetrics reporter
              │
              └── RUNNING STATE
                     │
                     ├── [Normal] grab → analyze → smooth → set_rgb (30 FPS)
                     ├── [Display event] pause / restart capture
                     ├── [Config change] hot-reload applicable settings
                     ├── [API call] update state, respond to UI
                     └── [Device disconnect] reconnect loop
```

---

## 3. Service Entry Point

```python
# ambilight/service/__main__.py
"""
Service entry point. Initialises all subsystems and blocks on uvicorn.
Run with: python -m ambilight.service
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import signal
import sys
from pathlib import Path

import uvicorn

from ambilight.config import ConfigManager
from ambilight.logging_setup import setup_logging
from ambilight.service.api_server import create_app
from ambilight.service.event_bus import EventBus
from ambilight.service.pipeline_controller import PipelineController
from ambilight.service.platform import get_display_monitor


DATA_DIR = Path(os.environ.get('AMBILIGHT_DATA_DIR', Path.home() / '.ambilight'))
AUTH_TOKEN_FILE = DATA_DIR / 'auth_token'
CONFIG_FILE = DATA_DIR / 'config.yaml'


def write_auth_token() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    AUTH_TOKEN_FILE.write_text(token)
    AUTH_TOKEN_FILE.chmod(0o600)
    return token


async def main() -> None:
    # Load configuration
    cfg = ConfigManager.load(CONFIG_FILE)
    
    # Setup logging
    metrics = setup_logging(
        level=cfg.logging.level,
        log_file=str(DATA_DIR / 'logs' / 'ambilight.log'),
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
        show_fps=cfg.logging.show_fps,
        fps_interval=cfg.logging.fps_interval,
    )
    
    log = logging.getLogger('ambilight.service')
    log.info("Ambilight Service starting. Data dir: %s", DATA_DIR)
    
    # Auth token
    token = write_auth_token()
    
    # Internal event bus
    bus = EventBus()
    
    # Display event watcher
    display_monitor = get_display_monitor(bus)
    display_monitor.start()
    
    # Pipeline controller (wraps existing pipeline logic)
    controller = PipelineController(cfg, bus, metrics)
    await controller.start()
    
    # HTTP/WebSocket API server
    app = create_app(controller, bus, token, cfg)
    
    config = uvicorn.Config(
        app,
        host='127.0.0.1',
        port=7826,
        log_level='warning',   # uvicorn is silent; we use our own logger
        loop='asyncio',
    )
    server = uvicorn.Server(config)
    
    # Graceful shutdown handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(controller, server)))
    
    log.info("Service ready. API on :7826, WebSocket on :7825")
    await server.serve()


async def shutdown(controller: PipelineController, server: uvicorn.Server) -> None:
    logging.getLogger('ambilight.service').info("Shutdown initiated.")
    await controller.stop()
    server.should_exit = True


if __name__ == '__main__':
    asyncio.run(main())
```

---

## 4. Pipeline Controller

```python
# ambilight/service/pipeline_controller.py
"""
PipelineController — manages the CaptureProcess lifecycle and reacts
to display events from the EventBus.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import time
from typing import Optional

from ambilight.config import AppConfig
from ambilight.service.event_bus import EventBus, EventType

log = logging.getLogger(__name__)


class PipelineController:
    """
    Manages the lifecycle of the capture + analysis + LED output pipeline.
    
    The capture loop runs in a separate Process to escape the GIL and
    prevent blocking the asyncio event loop that serves the API.
    Results are passed back via a multiprocessing.Queue.
    """
    
    def __init__(self, cfg: AppConfig, bus: EventBus, metrics) -> None:
        self._cfg = cfg
        self._bus = bus
        self._metrics = metrics
        self._process: Optional[mp.Process] = None
        self._result_queue: mp.Queue = mp.Queue(maxsize=5)
        self._running = False
        self._paused = False
        self._restart_delay = 2.0
        
        # Subscribe to display events
        bus.subscribe(EventType.SESSION_LOCKED,   self._on_lock)
        bus.subscribe(EventType.SESSION_UNLOCKED, self._on_unlock)
        bus.subscribe(EventType.SLEEP,            self._on_sleep)
        bus.subscribe(EventType.WAKE,             self._on_wake)
        bus.subscribe(EventType.DISPLAY_CHANGED,  self._on_display_changed)
        bus.subscribe(EventType.CONFIG_CHANGED,   self._on_config_changed)

    async def start(self) -> None:
        self._running = True
        await self._spawn_process()
        asyncio.create_task(self._result_consumer())

    async def stop(self) -> None:
        self._running = False
        await self._kill_process()

    async def pause(self, reason: str = '') -> None:
        if not self._paused:
            log.info("Pipeline paused. Reason: %s", reason)
            self._paused = True
            await self._kill_process()
            self._bus.emit(EventType.PIPELINE_STOPPED)

    async def resume(self, delay: float = 0.0) -> None:
        if self._paused:
            if delay > 0:
                await asyncio.sleep(delay)
            log.info("Pipeline resuming.")
            self._paused = False
            # Re-enumerate monitors before restarting
            await self._spawn_process()
            self._bus.emit(EventType.PIPELINE_STARTED)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_lock(self) -> None:
        await self.pause(reason='session locked')

    async def _on_unlock(self) -> None:
        # Wait 2 s for the compositor to fully restore before capturing
        await self.resume(delay=self._restart_delay)

    async def _on_sleep(self) -> None:
        await self.pause(reason='system sleep')

    async def _on_wake(self) -> None:
        # Wait longer after wake — GPU/display drivers take time to reinitialise
        await self.resume(delay=3.0)

    async def _on_display_changed(self) -> None:
        log.info("Display configuration changed — restarting capture.")
        await self.pause(reason='display change')
        await self.resume(delay=self._restart_delay)

    async def _on_config_changed(self) -> None:
        # Reload config and restart pipeline with new settings
        from ambilight.config import ConfigManager
        self._cfg = ConfigManager.get()
        log.info("Config reloaded — restarting pipeline.")
        await self.pause(reason='config change')
        await self.resume(delay=0.5)

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    async def _spawn_process(self) -> None:
        """Start a fresh CaptureProcess."""
        await self._kill_process()
        self._process = mp.Process(
            target=_capture_worker,
            args=(self._cfg, self._result_queue),
            daemon=True,
            name='ambilight-capture',
        )
        self._process.start()
        log.info("Capture process started (PID %d).", self._process.pid)

    async def _kill_process(self) -> None:
        """Terminate the CaptureProcess cleanly."""
        if self._process and self._process.is_alive():
            self._process.terminate()
            try:
                self._process.join(timeout=3.0)
            except Exception:
                self._process.kill()
        self._process = None

    async def _result_consumer(self) -> None:
        """
        Async task: drain results from the capture process and push to
        WebSocket subscribers.
        """
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                # Non-blocking check; yield to event loop between checks
                result = await loop.run_in_executor(
                    None, lambda: self._result_queue.get(timeout=0.1)
                )
                self._metrics.record_frame(result.get('latency_ms', 0))
                await self._bus.emit_async(EventType.METRICS_UPDATED, result)
            except Exception:
                pass


def _capture_worker(cfg: AppConfig, queue: mp.Queue) -> None:
    """
    Worker function that runs in a separate process.
    Executes the existing pipeline logic and pushes results to queue.
    """
    from ambilight.pipeline import AmbilightPipeline
    
    # The existing pipeline runs here, but instead of calling set_rgb directly
    # it pushes results through the queue for the LED output manager
    # in the parent process to transmit.
    pipeline = AmbilightPipeline(cfg, output_queue=queue)
    pipeline.start()
    pipeline.run()
```

---

## 5. Event Bus Design

```python
# ambilight/service/event_bus.py
"""
Internal publish/subscribe event bus using asyncio.
Thread-safe: events can be emitted from sync threads (e.g. display watcher)
and received by async coroutines (e.g. pipeline controller, WS broadcaster).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from enum import Enum, auto
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


class EventType(Enum):
    # Display / session events
    DISPLAY_CONNECTED    = auto()
    DISPLAY_DISCONNECTED = auto()
    DISPLAY_CHANGED      = auto()
    SESSION_LOCKED       = auto()
    SESSION_UNLOCKED     = auto()
    SLEEP                = auto()
    WAKE                 = auto()
    
    # Device events
    DEVICE_CONNECTED     = auto()
    DEVICE_DISCONNECTED  = auto()
    DEVICE_IP_CHANGED    = auto()
    DEVICE_DISCOVERED    = auto()
    
    # Pipeline events
    PIPELINE_STARTED     = auto()
    PIPELINE_STOPPED     = auto()
    PIPELINE_ERROR       = auto()
    
    # Config / profile events
    CONFIG_CHANGED       = auto()
    PROFILE_ACTIVATED    = auto()
    
    # Metrics
    METRICS_UPDATED      = auto()
    FPS_DEGRADED         = auto()


AsyncHandler = Callable[[Any], Coroutine]


class EventBus:
    """
    Async event bus with sync-compatible emit.
    
    Handlers are async coroutines. Emission from a sync context schedules
    the handlers on the running event loop via thread-safe call_soon_threadsafe.
    """
    
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[AsyncHandler]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None
    
    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
    
    def subscribe(self, event: EventType, handler: AsyncHandler) -> None:
        self._handlers[event].append(handler)
    
    def unsubscribe(self, event: EventType, handler: AsyncHandler) -> None:
        self._handlers[event].discard(handler)
    
    def emit(self, event: EventType, data: Any = None) -> None:
        """
        Emit from sync context (e.g. display watcher thread).
        Schedules handlers on the asyncio loop thread-safely.
        """
        if self._loop is None or not self._loop.is_running():
            return
        for handler in self._handlers[event]:
            self._loop.call_soon_threadsafe(
                lambda h=handler, d=data: asyncio.create_task(h(d))
            )
    
    async def emit_async(self, event: EventType, data: Any = None) -> None:
        """Emit from async context. Schedules handlers as concurrent tasks."""
        tasks = [asyncio.create_task(h(data)) for h in self._handlers[event]]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 6. Crash Recovery Strategy

### 6.1 Process-level restart (OS watchdog)

| Platform | Mechanism | Restart delay |
|---|---|---|
| Windows (NSSM) | `AppRestartDelay 5000` in NSSM config | 5 s |
| macOS (launchd) | `KeepAlive: true` | ~1–5 s |
| Linux (systemd) | `Restart=on-failure; RestartSec=5s` | 5 s |

The OS watchdog handles unexpected crashes (segfault, OOM, unhandled exception). The Python service does not need to implement its own watchdog for top-level crashes.

### 6.2 Internal subsystem recovery

Within a running service, individual subsystem failures are handled by the event bus:

```
CaptureProcess dies unexpectedly
  → PipelineController detects dead process (health check every 10 s)
  → Emits PIPELINE_ERROR event
  → Spawns new CaptureProcess
  → LED output manager continues with last known colour until new frames arrive

LED controller disconnects
  → MagicHomeController._send_raw() returns False
  → LED output manager enters reconnect loop (exponential back-off)
  → DeviceDiscovery scans subnet if reconnect fails 3× at configured IP
  → Emits DEVICE_DISCONNECTED / DEVICE_CONNECTED events
  → UI updates device status badge

API server crashes
  → uvicorn restarts its own worker (built-in restart strategy)
  → If uvicorn process dies entirely → OS watchdog restarts the whole service
```

### 6.3 State persistence before shutdown

On SIGTERM (normal shutdown) the service:
1. Sends `set_rgb(0, 0, 0)` + `turn_off()` to LED controller
2. Flushes log buffers
3. Writes current metrics snapshot to `~/.ambilight/metrics/latest.json`
4. Closes WebSocket connections (clients receive `1001 Going Away`)
5. Exits with code 0

On SIGKILL / crash, last-good state is recovered from `config.yaml` on restart.

---

## 7. Configuration Reload Strategy

Not all settings can be hot-reloaded. The service maintains three reload tiers:

| Tier | Examples | Action on change |
|---|---|---|
| **Hot** (no restart) | smoothing alpha, colour mode, zone count, LED brightness | Apply immediately to next pipeline tick |
| **Warm** (capture restart only) | FPS target, analysis resolution, monitor index | Restart CaptureProcess only; LED output continues |
| **Cold** (full service restart) | capture backend method, GPU preference, API port | Signal Electron to restart service |

```python
# In PipelineController._on_config_changed()
old_cfg = self._cfg
new_cfg = ConfigManager.get()

if _needs_cold_restart(old_cfg, new_cfg):
    await self._bus.emit_async(EventType.COLD_RESTART_REQUIRED)
elif _needs_warm_restart(old_cfg, new_cfg):
    await self.pause('config warm restart')
    self._cfg = new_cfg
    await self.resume(delay=0.5)
else:
    # Hot reload: just replace config reference
    self._cfg = new_cfg
    # Notify capture worker via shared Value or Queue message
    self._config_channel.put({'action': 'reload', 'config': new_cfg})
```

---

## 8. Logging Architecture

```
Logger hierarchy:
  ambilight                       ← root logger (all modules)
    ambilight.capture             ← backend switching events
    ambilight.color               ← analysis mode debug
    ambilight.smoothing           ← smoothing state (DEBUG only)
    ambilight.discovery           ← device scan results
    ambilight.led                 ← TCP send events, reconnects
    ambilight.service             ← lifecycle events
    ambilight.service.api         ← HTTP request logs
    ambilight.perf                ← FPS + latency stats (emitted at interval)

File: ~/.ambilight/logs/ambilight.log
  - Rotating: 5 MB × 3 backups
  - Format: timestamp | LEVEL | logger | message

WebSocket stream (filtered to WARNING+ by default, configurable):
  - Real-time log forwarding to UI log viewer
  - Level filter applied in api_server.py WebSocket handler
```

### 8.1 Structured log entries for UI

```python
# LogEntry pushed to WS clients
{
  "type": "log",
  "ts": 1748000000000,
  "payload": {
    "level": "WARNING",
    "logger": "ambilight.led",
    "message": "Send failed: [Errno 111] Connection refused — reconnecting.",
    "extra": {
      "ip": "192.168.1.29",
      "attempt": 1
    }
  }
}
```

---

## 9. Metrics Architecture

```python
# Metrics emitted via WebSocket every 500 ms
{
  "type": "metrics",
  "ts": 1748000000000,
  "payload": {
    "fps": 29.8,
    "capture_latency_ms": 12.3,
    "analysis_latency_ms": 1.8,
    "smoothing_latency_ms": 0.1,
    "led_latency_ms": 0.4,
    "total_latency_ms": 14.6,
    "zone_colors": [
      {"zone": "top_0", "r": 200, "g": 120, "b": 50},
      ...
    ],
    "device": {
      "connected": true,
      "ip": "192.168.1.29",
      "last_send_ms": 14
    },
    "capture": {
      "backend": "dxgi",
      "monitor": 0,
      "resolution": "1920x1080"
    },
    "gpu": {
      "backend": "cupy",
      "memory_mb": 12
    }
  }
}
```

Metrics are also persisted to `~/.ambilight/metrics/latest.json` as a rolling 60-second window for the Diagnostics page to render charts even after reconnecting to the UI.

---

## 10. Platform Capture Backends (Expansion)

### Linux — PipeWire Screen Capture

```python
# ambilight/capture.py — new backend
class PipeWireBackend(CaptureBackend):
    """
    Linux screen capture via PipeWire / xdg-desktop-portal.
    Required packages: python-gi, gstreamer1-plugins-pipewire
    Works on Wayland and X11 sessions.
    Does not require display server access; captures via portal API.
    """
    name = "pipewire"
    
    def open(self, monitor_index: int) -> bool:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        # PipeWire source via xdg-desktop-portal ScreenCast
        ...
```

### macOS — ScreenCaptureKit

```python
class ScreenCaptureKitBackend(CaptureBackend):
    """
    macOS 12.3+ native screen capture via ScreenCaptureKit.
    Provides the lowest latency and correctly handles DRM-protected content
    at the system level (same as QuickTime screen recording).
    Requires: pyobjc-framework-ScreenCaptureKit
    """
    name = "screencapturekit"
    
    def open(self, monitor_index: int) -> bool:
        import screencapturekit  # type: ignore
        ...
```

These backends are added to the `_candidates` list in `ScreenCaptureManager` with platform guards:

```python
if sys.platform == 'linux':
    candidates['pipewire'] = PipeWireBackend()
elif sys.platform == 'darwin':
    candidates['screencapturekit'] = ScreenCaptureKitBackend()
```
