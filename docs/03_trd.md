# Technical Requirements Document (TRD)
## Ambilight Desktop — System Architecture

**Version:** 1.0  
**Status:** Approved for Implementation  

---

## 1. System Architecture Overview

```
╔══════════════════════════════════════════════════════════════════╗
║                    USER MACHINE                                  ║
║                                                                  ║
║  ┌─────────────────────────────────────────────────────────┐   ║
║  │              ELECTRON APPLICATION                        │   ║
║  │  ┌──────────────┐  IPC   ┌───────────────────────────┐  │   ║
║  │  │  Main Process│◄──────►│    Renderer Process        │  │   ║
║  │  │  - tray      │        │  React + TypeScript + MUI  │  │   ║
║  │  │  - updater   │        │  Zustand state             │  │   ║
║  │  │  - svc ctrl  │        │  WebSocket client          │  │   ║
║  │  └──────┬───────┘        └───────────────────────────-┘  │   ║
║  └─────────│───────────────────────────────────────────────-┘   ║
║            │ WebSocket ws://127.0.0.1:7825                       ║
║            │ REST      http://127.0.0.1:7826                     ║
║            │                                                     ║
║  ┌─────────▼───────────────────────────────────────────────┐   ║
║  │         PYTHON SERVICE  (ambilight-service)              │   ║
║  │                                                          │   ║
║  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │   ║
║  │  │ServiceManager│  │  Config API  │  │  Event Bus    │  │   ║
║  │  │  + Watchdog  │  │  REST/WS     │  │  (internal)   │  │   ║
║  │  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │   ║
║  │         │                 │                   │           │   ║
║  │  ┌──────▼─────────────────▼───────────────────▼───────┐  │   ║
║  │  │            Pipeline Controller                       │  │   ║
║  │  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │  │   ║
║  │  │  │ Capture  │ │ Gradient │ │   Profile Manager  │  │  │   ║
║  │  │  │  Loop    │ │  Engine  │ │                    │  │  │   ║
║  │  │  └────┬─────┘ └────┬─────┘ └────────────────────┘  │  │   ║
║  │  │       │            │                                  │  │   ║
║  │  │  ┌────▼─────┐ ┌────▼──────┐ ┌────────────────────┐  │  │   ║
║  │  │  │  Display │ │  Effects  │ │  LED Device Layer  │  │  │   ║
║  │  │  │  Monitor │ │  Engine   │ │  + Capability Mgr  │  │  │   ║
║  │  │  └──────────┘ └───────────┘ └────────────────────┘  │  │   ║
║  │  └────────────────────────────────────────────────────-─┘  │   ║
║  └──────────────────────────────────────────────────────────--┘   ║
║                               │ TCP :5577                         ║
║                    ┌──────────▼──────────┐                       ║
║                    │  MagicHome Device   │                       ║
║                    └─────────────────────┘                       ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 2. Communication Layer Design

### 2.1 Technology Decision

The UI ↔ Service communication uses a **dual-channel architecture**:

| Channel | Protocol | Port | Purpose |
|---|---|---|---|
| Real-time stream | WebSocket | 7825 | FPS metrics, colour data, device status, log lines |
| Command/control | REST HTTP | 7826 | Config read/write, profile management, service control |

**Rationale for rejecting single-protocol alternatives:**

- **IPC (Electron's contextBridge):** Works only when UI and service are in the same process or spawned as a child. Our service must survive UI closure — IPC cannot work across independent processes.
- **gRPC:** Correct fit for bidirectional streaming, but requires protobuf schema compilation and is not natively supported in browser-origin Electron renderers without a gRPC-web proxy. Overhead is not justified for this scale.
- **WebSocket only:** Suitable for real-time data but REST-over-HTTP provides superior tooling for configuration: request/response semantics, HTTP status codes, `curl`-testable, OpenAPI documentable. REST is also essential for the planned web dashboard and mobile companion app.
- **REST only:** Cannot push sub-50 ms metrics to the UI without polling. Polling at 30 Hz creates unnecessary overhead and adds latency spikes.

**Final architecture:** REST for configuration, control, and one-off queries. WebSocket for continuous streaming of metrics, colour preview, and device events.

### 2.2 API Authentication

Both channels require a pre-shared token generated at service start and written to `~/.ambilight/auth_token`. The Electron main process reads this file and injects the token into all requests. Token rotates on each service restart.

```
Authorization: Bearer <token>   (REST)
?token=<token>                  (WebSocket handshake query parameter)
```

### 2.3 WebSocket Message Schema

```typescript
// All messages from service → UI
interface ServiceMessage {
  type: 'metrics' | 'device_event' | 'log' | 'state_change' | 'error';
  ts: number;       // Unix epoch ms
  payload: object;
}

// Metrics (emitted at 2 Hz)
interface MetricsPayload {
  fps: number;
  capture_latency_ms: number;
  analysis_latency_ms: number;
  led_latency_ms: number;
  zone_colors: Array<{ zone: string; r: number; g: number; b: number }>;
  device_connected: boolean;
  device_ip: string;
}

// Device events
interface DeviceEventPayload {
  event: 'connected' | 'disconnected' | 'ip_changed' | 'discovered';
  device: DeviceInfo;
}
```

### 2.4 REST API Specification

```
Base URL: http://127.0.0.1:7826/api/v1

# Health
GET  /health                    → ServiceHealth

# Service control
POST /service/start             → { ok: boolean }
POST /service/stop              → { ok: boolean }
POST /service/restart           → { ok: boolean }
GET  /service/status            → ServiceStatus

# Configuration
GET  /config                    → AppConfig
PUT  /config                    → AppConfig  (validates + hot-reloads)
GET  /config/schema             → JSON Schema

# Profiles
GET  /profiles                  → Profile[]
POST /profiles                  → Profile   (create)
GET  /profiles/:id              → Profile
PUT  /profiles/:id              → Profile   (update)
DELETE /profiles/:id            → { ok: boolean }
POST /profiles/:id/activate     → { ok: boolean }
GET  /profiles/:id/export       → file download
POST /profiles/import           → Profile   (multipart upload)

# Devices
GET  /devices                   → DeviceInfo[]
POST /devices/scan              → DeviceInfo[]  (trigger new scan)
POST /devices/:id/test          → TestResult
GET  /devices/:id/capabilities  → DeviceCapability

# Effects
GET  /effects                   → EffectDefinition[]
POST /effects/activate          → { ok: boolean }
GET  /effects/active            → EffectDefinition

# Diagnostics
GET  /diagnostics               → DiagnosticsReport
GET  /logs?level=INFO&n=200     → LogEntry[]
```

---

## 3. Service Architecture

### 3.1 Service Process Structure

```python
# Service entry point
ambilight/
  service/
    __main__.py          # Entry point: starts API server + pipeline
    api_server.py        # FastAPI app (REST + WebSocket)
    pipeline_controller.py  # Orchestrates start/stop/reload
    event_bus.py         # Internal pub/sub
    display_monitor.py   # OS display event watcher
    watchdog.py          # Self-monitoring + crash reporting
    gradient_engine.py   # Addressable LED gradient generation
    effects_engine.py    # Built-in and pluggable effects
    profile_manager.py   # Profile CRUD + activation
    capability_probe.py  # Device capability detection
    platform/
      __init__.py
      windows.py         # Windows service + display events
      macos.py           # launchd + ScreenCaptureKit
      linux.py           # systemd + udev + PipeWire
```

### 3.2 API Server

**Technology:** FastAPI + uvicorn (async, production-grade, auto-generates OpenAPI docs)

```python
# api_server.py (outline)
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Ambilight Service API", version="1.0")

# CORS locked to electron origin
app.add_middleware(CORSMiddleware, allow_origins=["null"])  # Electron file://

@app.get("/health")
async def health() -> ServiceHealth: ...

@app.websocket("/ws")
async def websocket_stream(ws: WebSocket): ...

@app.put("/config")
async def update_config(config: AppConfigModel) -> AppConfigModel: ...
```

The REST server runs on a separate `asyncio` thread from the capture pipeline (which is CPU-bound and runs in a `ProcessPoolExecutor` worker).

### 3.3 Internal Event Bus

```python
# event_bus.py
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, TypeVar
import asyncio

class EventType(Enum):
    DISPLAY_CONNECTED = auto()
    DISPLAY_DISCONNECTED = auto()
    DISPLAY_CHANGED = auto()
    SESSION_LOCKED = auto()
    SESSION_UNLOCKED = auto()
    SLEEP = auto()
    WAKE = auto()
    DEVICE_CONNECTED = auto()
    DEVICE_DISCONNECTED = auto()
    DEVICE_IP_CHANGED = auto()
    CONFIG_CHANGED = auto()
    PROFILE_ACTIVATED = auto()
    PIPELINE_STARTED = auto()
    PIPELINE_STOPPED = auto()
    PIPELINE_ERROR = auto()
    FPS_DEGRADED = auto()
```

Subscribers register typed async coroutines. Events are dispatched via `asyncio.create_task()` so that slow subscribers (e.g. logging to disk) do not block the capture loop.

### 3.4 Display Event Watcher

**Windows:**
```python
# platform/windows.py
import win32gui, win32con, threading

class WindowsDisplayMonitor:
    """
    Creates a hidden message-only window and processes:
      WM_DISPLAYCHANGE       → display resolution/count changed
      WM_WTSSESSION_CHANGE   → session lock/unlock
      WM_POWERBROADCAST      → sleep/wake (PBT_APMSUSPEND, PBT_APMRESUMEAUTOMATIC)
    """
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_DISPLAYCHANGE:
            self._bus.emit(EventType.DISPLAY_CHANGED)
        elif msg == win32con.WM_WTSSESSION_CHANGE:
            if wparam == win32con.WTS_SESSION_LOCK:
                self._bus.emit(EventType.SESSION_LOCKED)
            elif wparam == win32con.WTS_SESSION_UNLOCK:
                self._bus.emit(EventType.SESSION_UNLOCKED)
        elif msg == win32con.WM_POWERBROADCAST:
            if wparam == win32con.PBT_APMSUSPEND:
                self._bus.emit(EventType.SLEEP)
            elif wparam in (win32con.PBT_APMRESUMEAUTOMATIC, win32con.PBT_APMRESUMESUSPEND):
                self._bus.emit(EventType.WAKE)
```

**macOS:**
```python
# platform/macos.py
from AppKit import NSWorkspace, NSNotificationCenter

class MacOSDisplayMonitor:
    """
    Subscribes to NSWorkspace notifications:
      NSWorkspaceScreensDidWakeNotification
      NSWorkspaceScreensDidSleepNotification
      NSWorkspaceSessionDidBecomeActiveNotification
      NSWorkspaceSessionDidResignActiveNotification
    And CGDisplayRegisterReconfigurationCallback for display changes.
    """
```

**Linux:**
```python
# platform/linux.py
import subprocess, asyncio

class LinuxDisplayMonitor:
    """
    Watches udev events for drm device changes (monitor connect/disconnect).
    Reads /sys/class/drm/ for connected outputs.
    Subscribes to logind D-Bus signals for sleep/wake/session lock.
    """
```

### 3.5 Pipeline Controller

The `PipelineController` replaces `pipeline.py` as the main orchestrator. Key change: the capture loop runs in a `multiprocessing.Process` to escape the GIL and allow the API server to remain responsive.

```
PipelineController
  │
  ├── CaptureProcess (multiprocessing.Process)
  │     ├── ScreenCaptureManager
  │     ├── GpuAccelerator
  │     ├── ZoneManager
  │     ├── ColorAnalyzer
  │     └── SmoothingEngine
  │
  ├── LEDOutputManager (thread in main process)
  │     └── MagicHomeController (TCP)
  │
  ├── GradientEngine
  ├── EffectsEngine
  └── ProfileManager
```

The `CaptureProcess` sends colour results via a `multiprocessing.Queue` to the `LEDOutputManager` in the main process. This decouples capture latency from TCP send latency.

---

## 4. Component Architecture

### 4.1 Gradient Engine

```python
# gradient_engine.py

@dataclass
class GradientSpec:
    mode: Literal['linear', 'radial', 'ambient', 'screen_matched']
    led_count: int
    gamma: float = 2.2
    blend_mode: Literal['linear_rgb', 'oklab', 'hsl'] = 'oklab'

class GradientEngine:
    """
    Converts per-zone colours into a per-LED colour array.

    For addressable strips, outputs an array of shape (led_count, 3).
    For single-RGB hardware, outputs a single (3,) best-representative colour.

    Colour interpolation is performed in OKLab colour space for perceptually
    uniform transitions, then gamma-corrected for physical LED response.
    """
    def generate(
        self,
        zone_colors: list[tuple[Zone, tuple[int,int,int]]],
        spec: GradientSpec,
    ) -> np.ndarray:
        ...
    
    def _interpolate_oklab(
        self, c1: np.ndarray, c2: np.ndarray, t: float
    ) -> np.ndarray:
        """Linear interpolation in OKLab perceptual space."""
        ...

    def _apply_gamma(self, linear: np.ndarray, gamma: float) -> np.ndarray:
        return np.power(linear / 255.0, 1.0 / gamma) * 255.0
```

### 4.2 Capability Probe

```python
# capability_probe.py

@dataclass
class DeviceCapability:
    supports_single_rgb: bool = True
    supports_zones: bool = False
    zone_count: int = 1
    supports_addressable: bool = False
    led_count: int = 1
    supports_hardware_effects: bool = False
    firmware_version: str = ""
    model_id: str = ""

class CapabilityProbe:
    """
    Interrogates a MagicHome device to determine its capabilities.
    
    Sends model query commands and observes response length and structure.
    Devices with addressable support respond to extended protocol commands.
    Single-RGB controllers respond only to basic RGB set commands.
    """
    def probe(self, ip: str, port: int = 5577) -> DeviceCapability: ...
```

### 4.3 Plugin Architecture

Effects plugins are Python modules placed in `~/.ambilight/plugins/`.

```python
# Plugin interface (plugins/base.py)
from abc import ABC, abstractmethod
import numpy as np

class EffectPlugin(ABC):
    name: str = "unnamed"
    description: str = ""
    version: str = "0.1.0"
    
    @abstractmethod
    def tick(
        self,
        frame: np.ndarray,         # Current BGR frame at analysis resolution
        zone_colors: list,         # Current zone colour list
        elapsed: float,            # Seconds since effect started
        config: dict,              # Plugin-specific config dict
    ) -> tuple[int, int, int]:     # Final (R, G, B) to output
        ...
    
    def on_activate(self, config: dict) -> None:
        """Called when this effect becomes active."""
    
    def on_deactivate(self) -> None:
        """Called when switching away from this effect."""
```

### 4.4 Persistence Architecture

```
~/.ambilight/                           # User data root
  config.yaml                           # Active configuration (atomic writes)
  auth_token                            # Service API token
  device_cache.json                     # Discovered device cache
  profiles/
    builtin/
      gaming.json
      movie.json
      productivity.json
      night.json
    user/
      my_custom_profile.json
  plugins/
    my_audio_effect.py
  logs/
    ambilight.log
    ambilight.log.1
    ambilight.log.2
  metrics/
    latest.json                         # Last 60 seconds of FPS/latency data
```

All writes to `config.yaml` and profile JSON files use the write-to-temp-then-rename pattern for atomicity.

---

## 5. Electron Architecture

### 5.1 Process Map

```
Electron Main Process (Node.js)
  │
  ├── BrowserWindow (Renderer — React App)
  │     └── contextBridge → ipcRenderer
  │
  ├── Tray Icon + Context Menu
  ├── Auto Updater (electron-updater)
  ├── Service Controller
  │     ├── Start/Stop Python service process
  │     ├── Read auth_token from disk
  │     └── Health-check polling
  │
  └── WebSocket Client → ws://127.0.0.1:7825
        └── Forwards messages to Renderer via IPC
```

### 5.2 IPC Channel Design

```typescript
// preload.ts — exposed to renderer
contextBridge.exposeInMainWorld('ambilightAPI', {
  // Service control
  startService: () => ipcRenderer.invoke('service:start'),
  stopService: () => ipcRenderer.invoke('service:stop'),
  restartService: () => ipcRenderer.invoke('service:restart'),

  // Config
  getConfig: () => ipcRenderer.invoke('config:get'),
  setConfig: (config) => ipcRenderer.invoke('config:set', config),

  // Real-time events from service
  onMetrics: (cb) => ipcRenderer.on('ws:metrics', (_, data) => cb(data)),
  onDeviceEvent: (cb) => ipcRenderer.on('ws:device_event', (_, data) => cb(data)),
  onLog: (cb) => ipcRenderer.on('ws:log', (_, data) => cb(data)),
  
  // Profile management
  getProfiles: () => ipcRenderer.invoke('profiles:get'),
  activateProfile: (id) => ipcRenderer.invoke('profiles:activate', id),
});
```

### 5.3 State Management

Zustand store structure:

```typescript
interface AppStore {
  // Service state
  serviceStatus: 'running' | 'stopped' | 'starting' | 'stopping' | 'error';
  serviceError: string | null;

  // Metrics
  metrics: MetricsPayload | null;

  // Configuration
  config: AppConfig | null;
  configDirty: boolean;

  // Devices
  devices: DeviceInfo[];

  // Profiles
  profiles: Profile[];
  activeProfile: string | null;

  // Effects
  activeEffect: string;

  // Logs
  logs: LogEntry[];

  // Actions
  startService: () => Promise<void>;
  stopService: () => Promise<void>;
  saveConfig: () => Promise<void>;
  activateProfile: (id: string) => Promise<void>;
}
```

---

## 6. Platform Service Architecture

### 6.1 Service Manager Abstraction

```python
# service/platform/base.py
from abc import ABC, abstractmethod

class PlatformServiceManager(ABC):
    service_name: str = "ambilight-service"
    display_name: str = "Ambilight Desktop Service"

    @abstractmethod
    def install(self, executable_path: str, args: list[str]) -> bool: ...

    @abstractmethod
    def uninstall(self) -> bool: ...

    @abstractmethod
    def start(self) -> bool: ...

    @abstractmethod
    def stop(self) -> bool: ...

    @abstractmethod
    def restart(self) -> bool: ...

    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def set_auto_start(self, enabled: bool) -> bool: ...

    @abstractmethod
    def get_status(self) -> dict: ...
```

### 6.2 Windows Service (NSSM)

The service is registered using NSSM (Non-Sucking Service Manager) embedded in the installer. NSSM provides automatic restart, stdout/stderr capture, and registry-based configuration — all without requiring the Python script to implement the Windows Service Control Manager protocol.

```
nssm install ambilight-service "C:\...\ambilight\python\python.exe"
nssm set ambilight-service AppParameters "-m ambilight.service"
nssm set ambilight-service AppDirectory "C:\...\ambilight"
nssm set ambilight-service Start SERVICE_AUTO_START
nssm set ambilight-service AppRestartDelay 5000
nssm set ambilight-service AppStdout "C:\...\logs\service.log"
nssm set ambilight-service AppStderr "C:\...\logs\service_err.log"
```

### 6.3 macOS (launchd)

```xml
<!-- ~/Library/LaunchAgents/com.ambilight.service.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ambilight.service</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/Ambilight.app/Contents/Resources/python/bin/python3</string>
        <string>-m</string>
        <string>ambilight.service</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>~/.ambilight/logs/service.log</string>
    <key>StandardErrorPath</key>
    <string>~/.ambilight/logs/service_err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AMBILIGHT_DATA_DIR</key>
        <string>~/.ambilight</string>
    </dict>
</dict>
</plist>
```

### 6.4 Linux (systemd user service)

```ini
# ~/.config/systemd/user/ambilight.service
[Unit]
Description=Ambilight Desktop Service
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=/opt/ambilight/python/bin/python3 -m ambilight.service
Restart=on-failure
RestartSec=5s
Environment=AMBILIGHT_DATA_DIR=%h/.ambilight
StandardOutput=append:%h/.ambilight/logs/service.log
StandardError=append:%h/.ambilight/logs/service_err.log

[Install]
WantedBy=default.target
```

---

## 7. Security Architecture

### 7.1 Threat model

| Threat | Mitigation |
|---|---|
| Local process reads API token | Token stored in `~/.ambilight/auth_token`, mode 0600 |
| Network exposure of API | API binds to 127.0.0.1 only; no `0.0.0.0` |
| Config file injection | YAML loaded with `yaml.safe_load` (no arbitrary code) |
| Electron renderer XSS → IPC abuse | contextBridge whitelist; no `nodeIntegration: true` |
| Plugin code execution | Plugins run in a sandboxed `RestrictedPython` evaluator (P3) |
| Auto-update MITM | Updates served over HTTPS; installer signed with code-signing cert |

### 7.2 Electron security configuration

```javascript
// main/window.ts
new BrowserWindow({
  webPreferences: {
    nodeIntegration: false,       // CRITICAL: never enable
    contextIsolation: true,       // CRITICAL: always enabled
    sandbox: true,                // Renderer process sandboxed
    preload: path.join(__dirname, 'preload.js'),
  }
});
```

---

## 8. Packaging Architecture

### 8.1 Build outputs

| Platform | Format | Tool |
|---|---|---|
| Windows | NSIS installer (.exe) | electron-builder |
| Windows | MSI installer (.msi) | electron-builder |
| macOS | Signed DMG | electron-builder + Apple codesign |
| Linux | AppImage | electron-builder |
| Linux | .deb | electron-builder |
| Linux | .rpm | electron-builder |

### 8.2 Bundled Python runtime

Python is bundled via **PyInstaller** (Windows/Linux) or **py2app** (macOS), producing a self-contained `python/` directory inside the application bundle. No system Python is required.

```
electron-builder
  extraResources:
    - from: dist/service/          # PyInstaller output
      to: service/
```

### 8.3 Auto-update

Using `electron-updater`:
- Update server: GitHub Releases (self-hosted option available)
- Check interval: 24 hours + on app launch
- User prompted before install; silent install available in enterprise config
- Differential updates for Python service bundle (only changed files)

---

## 9. Data Flow Diagram

```
Display                  Service Process              LED Hardware
  │                           │
  │  screen pixels             │
  ├──────────────────────────►│
  │  WGC/DXGI/MSS grab()      │
  │                           │ 80×45 BGR array
  │                           ├───[GPU resize]──────────────┐
  │                           │                             │
  │                           │◄────────────────────────────┘
  │                           │ analyze zones (NumPy)
  │                           │ smooth colours (EMA)
  │                           │ gradient map (OKLab)
  │                           │
  │                           ├──[TCP :5577]──────────────►LED
  │                           │
  │                    ┌──────▼────────┐
  │                    │  WS stream    │ ──► Electron UI
  │                    │  (2 Hz)       │     (colour preview,
  │                    └───────────────┘      FPS, status)
  │
Display events
  lock/unlock/sleep/wake
  ├──────────────────────────►│
  │  DisplayEventWatcher       │ EventBus.emit()
  │                           ├──► PipelineController
  │                           │     → pause / restart capture
```

---

## 10. Configuration Schema (JSON Schema fragment)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "title": "AmbilightConfig",
  "type": "object",
  "properties": {
    "capture": {
      "type": "object",
      "properties": {
        "method": { "type": "string", "enum": ["wgc", "dxgi", "mss"] },
        "monitor_index": { "type": "integer", "minimum": 0 },
        "fps_target": { "type": "integer", "minimum": 5, "maximum": 60 },
        "analysis_width": { "type": "integer", "minimum": 20, "maximum": 320 },
        "analysis_height": { "type": "integer", "minimum": 11, "maximum": 180 }
      }
    },
    "device": {
      "type": "object",
      "properties": {
        "ip": { "type": "string", "format": "ipv4" },
        "mac": { "type": "string", "pattern": "^([0-9a-f]{2}:){5}[0-9a-f]{2}$|^$" }
      }
    }
  }
}
```

Full schema is served at `GET /api/v1/config/schema` and used by the Electron UI to render dynamic settings forms.
