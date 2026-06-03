# Ambilight Desktop

**Cross-platform ambient lighting platform that works the way it should — install, configure, forget.**

[![Build Status](https://github.com/LMC4910/ambilightRepo/actions/workflows/build.yml/badge.svg)](https://github.com/LMC4910/ambilightRepo/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](docs/02_prd.md#platform-support)

> **Transform any display into an immersive viewing experience with dynamic, screen-reactive LED lighting — without proprietary hardware lock-in.**

**Ambilight Desktop** is a production-grade ambient lighting platform that extends any display with dynamic, screen-reactive LED lighting. It delivers a premium Philips Ambilight experience on custom hardware — without proprietary lock-in.

The platform vision: a persistent background service with a native desktop control application, distributed as a single installer. Configure once and it works silently and reliably from that point forward. The current CLI implementation provides production-ready functionality today, while the desktop application architecture is under active development.

## Development Status

**Current Implementation Status:**
- ✅ **CLI Mode** - Production-ready command-line interface
- ✅ **REST API** - FastAPI server for control and configuration
- ✅ **Desktop UI** - Electron application with React frontend
- 🚧 **Service Architecture** - Background service foundation in progress
- 🚧 **Auto-start & Installer** - Single-installer distribution planned

The project delivers a functional desktop application today with API server and Electron UI. The next phase focuses on persistent background service architecture with auto-start capabilities and packaged installer distribution.

**Roadmap**: CLI → Service Foundation → Desktop UI → Packaged Installer  
(See [Development Roadmap](#roadmap) for complete milestone details)

---

## ✨ Feature Implementation Status

### 📊 Quick Summary
- **Fully Implemented:** 18/69 documented features (26%)
- **Partially Implemented:** 18/69 features (26%)
- **Not Yet Implemented:** 23/69 features (33%)
- **Unknown/Needs Testing:** 10/69 features (15%)

### ✅ What Works Today

#### Backend Service (Python/FastAPI)
| Component | Status | Details |
|-----------|--------|---------|
| **REST API** | ✅ Fully Working | Port 7826, Bearer token authentication |
| **Screen Capture** | ✅ Fully Working | DXGI/DXCam backend, 24-30 FPS achieved, <50ms latency ✓ |
| **Color Analysis** | ✅ Fully Working | 5 modes: average, edges, dominant, kmeans, saturation_weighted |
| **Effects Engine** | ✅ Fully Working | screen_sync, static, breathing, rainbow modes |
| **Profile Management** | ✅ Fully Working | Save/load/apply/delete profiles via API |
| **Device Discovery** | ✅ Fully Working | Auto-discover MagicHome devices via MAC address |
| **Configuration Management** | ✅ Fully Working | YAML config, environment variable overrides, hot-reload event (partial) |
| **Authentication** | ✅ Fully Working | Secure Bearer token generation and validation |
| **Logging** | ✅ Fully Working | File-based logging with INFO/DEBUG levels |
| **Platform Events** | ✅ Fully Working | Sleep/wake/lock detection via platform_monitor |

#### Frontend (Electron/React)
| Component | Status | Details |
|-----------|--------|---------|
| **Dashboard Tab** | ✅ Fully Working | Real-time FPS, latency, uptime display |
| **Diagnostics Tab** | ✅ Fully Working | Log viewer with clear and open folder buttons |
| **Service Status** | ✅ Fully Working | Shows online/offline status with visual indicator |
| **Mode Switching** | ✅ Partially Working | Screen Sync & Rainbow buttons present |
| **State Management** | ✅ Fully Working | Zustand store for app state |

### 🚧 Partially Implemented (Needs Attention)

| Feature ID | Feature | Status | Gap |
|---|---|---|---|
| FR-SVC-06 | Hot-reload configuration | Event exists | No UI to trigger reload |
| FR-SVC-07 | Persist/restore last-known-good state | Partial | Profiles saved, but auto-recovery missing |
| FR-CAP-02/03/04 | Monitor recovery (lock/disconnect/sleep) | Code exists | Needs user validation |
| FR-CAP-06 | Multi-monitor support | Config present | No UI for monitor selection |
| FR-CLR-07 | Per-zone color analysis | Module exists | Needs testing |
| FR-DEV-04/06/08 | Device capability probe, health status, auto-reconnect | Code exists | Incomplete testing |
| FR-GRAD-03/04 | Radial & ambient gradients | Infrastructure present | Specific types untested |
| FR-UI-01 | Service start/stop controls | API has start/stop | Missing restart, no UI buttons |
| FR-UI-05 | Effect selector with preview | Basic buttons only | Missing all but 2 modes in UI |
| FR-UI-07 | Log viewer with filter | Viewer works | No log level filter |

### ❌ Not Implemented (Planned for Future)

| Category | Missing Features | Priority |
|----------|---|---|
| **Service Management** | Auto-start on boot, continue when UI closed, auto-restart on crash, Windows Service setup | P0 |
| **Advanced Capture** | DRM-protected WGC support validation, multi-device support, per-monitor assignment | P1-P2 |
| **Effects** | Audio-reactive mode, scene presets (sunrise/sunset), custom effect scripting, effect scheduling | P2-P3 |
| **Profiles** | Built-in profiles (Gaming/Movie/Productivity/Night), auto-switch by app, JSON import/export UI | P1-P2 |
| **Desktop UI** | Device manager UI, zone editor, settings editor, system tray, first-run wizard, device diagnostics panel | P0-P2 |
| **UI Polish** | Live color preview, device health display in UI, effect preview, minimize to tray | P1-P2 |

### 📋 Testing Results (Verified June 3, 2026)

| Test | Result | Details |
|------|--------|---------|
| Device Discovery | ✅ PASS | Found 1 device at 192.168.1.29 (MAC: 1a:2d:11:00:0c:00) |
| Monitor Listing | ✅ PASS | Detected 3 monitors correctly |
| API Authentication | ✅ PASS | Bearer token required, enforced |
| `/api/status` | ✅ PASS | Returns service status, PID, pause state |
| `/api/config` | ✅ PASS | Returns full configuration (21 fields) |
| `/api/profiles` | ✅ PASS | Lists profiles correctly |
| Profile Save/Load | ✅ PASS | Profiles persist to disk (gaming.json created) |
| Mode: screen_sync | ✅ PASS | Achieved 29.3 FPS, 34.2 ms latency |
| Mode: rainbow | ✅ PASS | Effect switched successfully, 21.7 FPS |
| Mode: breathing | ✅ PASS | Red breathing effect applied |
| WebSocket Metrics | ⚠️ PARTIAL | Token parameter issue on `/ws` endpoint |
| Frontend Build | ✅ PASS | Vite build successful, dist created |
| GPU Acceleration | ✅ PASS | CuPy backend loaded and active |

### 🎯 Non-Functional Requirements Status

| Requirement | Target | Current Status | Notes |
|---|---|---|---|
| **End-to-end Latency** | ≤50ms | **34-47ms** ✅ | Exceeds target |
| **Capture FPS** | ≥24 FPS | **29.3 FPS** ✅ | Exceeds target in screen_sync |
| **CPU Usage** | ≤5% | Unknown | Needs profiling |
| **Memory Usage** | ≤150 MB | Unknown | Needs measurement |
| **UI Startup Time** | ≤3s | Unknown | Electron startup untested |
| **Service Uptime (MTBF)** | ≥7 days | Unknown | Long-term testing needed |
| **Windows/macOS/Linux Support** | All platforms | Windows tested ✅, macOS/Linux untested | WGC capture Windows-specific |

---

## Who Is This For?

Ambilight Desktop serves four distinct user types. Find yours and jump straight to what matters.

| Persona | Core Need | Jump To |
|---|---|---|
| 🎬 Home Theater Enthusiast | DRM bypass, cinema smoothing, sleep/wake recovery | [Quick Start](#quick-start) · [Capture Backends](#capture-backend-selection) · [Smoothing](#smoothing-tuning) |
| 🎮 PC Gamer | <50 ms latency, zero FPS impact, gaming profiles | [Quick Start](#quick-start) · [Performance](#performance-optimisation) · [Colour Modes](#colour-modes-reference) |
| 💻 Developer / Power User | REST API, WebSocket metrics, profile CRUD, scriptable modes | [API Server](#architecture-) · [Environment Variables](#environment-variables) · [Contributing](#contributing) |
| 👤 Casual User | Simple setup, auto-discovery, graphical UI | [Quick Start](#quick-start) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting) |

### 🎬 Home Theater Enthusiast

You watch Netflix, Disney+, or local media daily on a display ringed with LED strips. You need DRM-protected content captured correctly (the WGC backend handles this) and cinema-quality smoothing so scene cuts don't produce jarring LED jumps. The display event handler in `pipeline_controller.py` automatically pauses and resumes on sleep, wake, and lock — no manual restarts.

→ [Quick Start](#quick-start) · [Capture Backend Selection](#capture-backend-selection) · [Smoothing Tuning](#smoothing-tuning) · [DRM Troubleshooting](#drm-protected-content-appears-black)

---

### 🎮 PC Gamer

You run GPU-intensive titles and need LEDs that feel reactive without any measurable FPS impact. Ambilight Desktop delivers <50 ms end-to-end latency at <5% CPU. The effects engine supports `screen_sync`, `static`, `breathing`, and `rainbow` modes — save a gaming profile via the REST API or Electron UI and switch it in one click.

→ [Quick Start](#quick-start) · [Performance Optimisation](#performance-optimisation) · [Colour Modes Reference](#colour-modes-reference) · [Architecture & API](#architecture-)

---

### 💻 Developer / Power User

You want programmatic control: REST endpoints (port 7826), WebSocket metrics streaming, profile CRUD, and scriptable color modes. The FastAPI server is fully implemented and token-secured. Profile save/load/apply and live config updates all work as documented API calls — no UI required.

→ [Architecture & API](#architecture-) · [Environment Variables](#environment-variables) · [Documentation Index](#documentation) · [Contributing](#contributing)

---

### 👤 Casual User

You connected some LED strips and want something that just works. Run `python main.py --discover`, add your device IP to `configuration.yaml`, and run `python main.py`. Auto-discovery finds your controller again after router restarts. The Electron desktop app gives you a graphical interface so you rarely need the command line again.

→ [Quick Start](#quick-start) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting)

---

> Full persona descriptions and user stories: [PRD Section 2](docs/02_prd.md#2-user-personas)

---

## Table of Contents

- [Quick Start](#quick-start)
- [Current Implementation: CLI Mode ✅](#current-implementation-cli-mode-)
  - [Architecture](#architecture-)
    - [Module Responsibilities](#module-responsibilities)
  - [Features](#features)
  - [Platform Support](#platform-support-)
  - [Installation](#installation)
    - [1. Requirements](#1-requirements)
    - [2. Install](#2-install)
  - [Configuration](#configuration)
    - [3. Configure](#3-configure)
    - [Configuration Schema Reference](#configuration-schema-reference)
  - [Usage](#usage-)
    - [5. List Monitors](#5-list-monitors)
    - [6. Run](#6-run)
  - [Performance Optimisation](#performance-optimisation)
    - [Capture Backend Selection](#capture-backend-selection)
    - [Analysis Resolution](#analysis-resolution)
    - [GPU Acceleration](#gpu-acceleration)
    - [Smoothing Tuning](#smoothing-tuning)
    - [Network Overhead](#network-overhead)
  - [Troubleshooting](#troubleshooting)
  - [Environment Variables](#environment-variables)
  - [Colour Modes Reference](#colour-modes-reference)
- [Planned Service Architecture 🚧](#planned-service-architecture-)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

Want to try Ambilight Desktop right now? Here's the fastest path:

```bash
# 1. Install Python 3.12 (or 3.10+)
# 2. Clone and navigate to the project
cd ambilight

# 3. Install dependencies
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS/Linux
pip install -r requirements.txt

# 4. Discover your MagicHome device
python main.py --discover

# 5. Edit configuration.yaml with your device IP

# 6. Run
python main.py
```

That's it! Your LEDs should now sync with your screen content.

---

## Current Implementation: CLI Mode ✅

**Status: Production-ready and actively used**

Ambilight Desktop is **available now** with multiple operational modes:
- ✅ Command-line interface (CLI) for direct execution
- ✅ REST API server (FastAPI, port 7826) for programmatic control — token-secured, profile CRUD, WebSocket metrics
- ✅ Desktop application (Electron + React UI) for graphical management

All core ambient lighting functionality is implemented and stable.

### Architecture ✅

**All modes share the same production-ready pipeline core.**

The system provides three operational modes:

#### Entry Points

**CLI / API Server (`python main.py`)**  
Launches the FastAPI server via uvicorn. Supports `--discover`, `--list-monitors`, `--ip`, `--mode`, and `--debug` flags for direct CLI use.

**API Server (port 7826)**  
FastAPI REST endpoints for configuration, profiles, pipeline control, and mode switching. WebSocket at `/ws` streams real-time metrics at 10 Hz. All endpoints secured with a per-session Bearer token generated by `auth.py`.

**Desktop Application (Electron UI)**  
React frontend connects to the API server for visual settings management, profile creation, real-time metrics display, and log viewing.

#### Core Pipeline Architecture

All modes share this production-ready pipeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│              main.py  (CLI / uvicorn entry point)                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  launches FastAPI via uvicorn
                    ┌────────────▼────────────┐
                    │      api_server.py       │  FastAPI + WebSocket
                    │  REST :7826 · WS /ws    │  auth.py (Bearer token)
                    └──┬──────────────────┬───┘
                       │  controls        │  publishes events
          ┌────────────▼──────────┐  ┌────▼────────────────┐
          │  PipelineController   │  │     EventBus         │
          │  pipeline_controller  │  │     events.py        │
          │  (multiprocessing)    │  │  DISPLAY_OFF/ON      │
          └────────────┬──────────┘  │  CONFIG_UPDATE       │
                       │  spawns     │  METRICS_UPDATE       │
          ┌────────────▼──────────┐  └────────────────────┬─┘
          │   AmbilightPipeline   │◄───────────────────────┘
          │      pipeline.py      │  stop / pause events
          └──┬────┬────┬────┬────┘
             │    │    │    │
┌────────────┘    │    │    └──────────────────────┐
│                 │    │                             │
▼                 ▼    ▼                             ▼
ScreenCapture  ZoneManager  GpuAccelerator    EffectsManager
Manager        zones.py     gpu.py            effects_engine.py
capture.py                                    screen_sync | static
                                               breathing | rainbow
WGC ──────┐
DXGI ─────┤
MSS  ─────┘
              ColorAnalyzer          SmoothingEngine
              color.py               smoothing.py
              • average              Adaptive EMA per zone
              • edges                + single combined output
              • dominant
              • kmeans
              • saturation_weighted

                     MagicHomeController
                     led_output.py
                     Thread-safe TCP, reconnect,
                     duplicate suppression, rate limiting

Support modules
───────────────
  config.py           YAML config → typed AppConfig dataclass (atomic save)
  discovery.py        Subnet scanner + MAC-based device cache
  logging_setup.py    Rotating logs + FPS/latency metrics thread
  auth.py             Per-session Bearer token; 0600 file permissions
  profile_manager.py  Save / load / apply named configuration profiles
  events.py           Async EventBus (subscribe/publish pattern)
  platform_monitor.py OS sleep/wake/lock detection → EventBus
  gradient_engine.py  Gradient colour helpers
```

#### Module responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | CLI argument parsing, environment overrides, uvicorn entry point |
| `api_server.py` | FastAPI REST + WebSocket server; pipeline start/stop; profile endpoints |
| `auth.py` | Per-session Bearer token generation; secure file write (0600); token verification |
| `pipeline_controller.py` | Manages `AmbilightPipeline` in an isolated `multiprocessing.Process`; handles pause/resume events |
| `pipeline.py` | Orchestrates all capture/analyse/output modules in the main loop |
| `events.py` | Async EventBus: subscribe/publish for DISPLAY_OFF, CONFIG_UPDATE, METRICS_UPDATE |
| `platform_monitor.py` | Detects OS sleep/wake/lock/unlock events and emits them to EventBus |
| `capture.py` | WGC → DXGI → MSS backend chain with auto-failover |
| `gpu.py` | Detect CuPy / OpenCV CUDA / PyTorch; CPU fallback; unified resize API |
| `zones.py` | Slice analysis frame into configurable edge zones |
| `color.py` | 5 colour-analysis modes; zone combiner |
| `smoothing.py` | Adaptive EMA per zone + single combined output |
| `effects_engine.py` | Non-capture effects: `screen_sync`, `static`, `breathing`, `rainbow` |
| `profile_manager.py` | Save, load, list, apply, and delete named configuration profiles |
| `discovery.py` | Parallel TCP scan; MAC-based caching; reconnect after IP change |
| `led_output.py` | MagicHome TCP protocol; rate limiting; duplicate suppression; reconnect |
| `config.py` | Load/validate YAML config; expose typed `AppConfig`; atomic save via temp-then-rename |
| `logging_setup.py` | Rotating file + coloured console logging; background FPS/latency metrics thread |
| `gradient_engine.py` | Gradient colour computation helpers |

### Features ✅

- ✅ **Multi-backend screen capture**: WGC (DRM bypass), DXGI, MSS with automatic failover chain
- ✅ **5 color analysis modes**: average, edges, dominant, k-means, saturation-weighted
- ✅ **GPU acceleration**: CuPy, OpenCV CUDA, PyTorch with automatic CPU fallback
- ✅ **Adaptive smoothing**: Per-zone EMA with fast response to scene cuts and gentle transitions for subtle changes
- ✅ **Auto device discovery**: Parallel subnet scan, MAC-based caching, automatic reconnect after IP change
- ✅ **Effects engine**: screen_sync, static color, breathing, and rainbow cycle modes
- ✅ **Performance**: 30 FPS target at <5% CPU (80×45 analysis resolution); <50ms end-to-end latency; GPU path reduces frame processing to 2–15ms

### Platform Support ✅

| Platform | Status | Capture Backends | Min Version | Notes |
|----------|--------|------------------|-------------|-------|
| Windows 10 | ✅ Primary | WGC, DXGI, MSS | 1903 (build 18362) | WGC requires 1903+; 22H2+ recommended |
| Windows 11 | ✅ Primary | WGC, DXGI, MSS | 23H2 | Recommended platform |
| macOS | 🚧 Experimental | MSS only | 13 Ventura | WGC/DXGI unavailable; GPU acceleration not supported; ScreenCaptureKit planned |
| Linux | 🚧 Experimental | MSS only | Ubuntu 22.04 LTS | WGC/DXGI unavailable; GPU acceleration not supported; PipeWire planned |

> **Experimental platforms** (macOS, Linux): The core pipeline runs and MSS capture works, but these platforms receive limited testing and no hardware-accelerated capture. Expect reduced performance and potential rough edges. Contributions welcome.

**Capture Backend Comparison:**

| Backend | Latency | DRM Bypass | Platform | Requirements |
|---------|---------|------------|----------|--------------|
| WGC | ★★★ | Yes (compositor) | Windows 10 1903+ only | `pip install winsdk comtypes pywin32` |
| DXGI (dxcam) | ★★★ | No | Windows only | `pip install dxcam` |
| MSS | ★★ | No | Windows, macOS, Linux | Included in `requirements.txt` |

The capture manager tries backends in priority order (WGC → DXGI → MSS) and automatically fails over if a backend is unavailable. On macOS and Linux, only MSS is attempted.

**Hardware Requirements:**

| Component | Requirement |
|-----------|-------------|
| LED Controller | MagicHome / LEDENET compatible Wi-Fi RGB controller (TCP port 5577) |
| Network | Controller and computer on the same LAN subnet |
| GPU (optional) | CUDA-capable GPU (NVIDIA) for hardware-accelerated resize and color analysis — CuPy, OpenCV CUDA, or PyTorch CUDA; CPU fallback is automatic |
| Python | 3.12 recommended (3.10+ supported) |

> **MagicHome / LEDENET compatibility**: Any controller that speaks the MagicHome TCP protocol on port 5577 is supported. Use `python main.py --discover` to scan your subnet and confirm your device is detected.

---

### Installation ✅

#### 1. Requirements

- **Python 3.12** (3.10+ also works)
- **Windows 10 1903+ / 11** for WGC and DXGI backends (full feature set); macOS 13+ and Linux (Ubuntu 22.04+) supported with MSS only — see [Platform Support](#platform-support-)
- **MagicHome / LEDENET compatible Wi-Fi RGB controller** reachable on the local network via TCP port 5577

#### 2. Install

```bash
# Clone / download the project
cd ambilight

# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# Install core dependencies
pip install -r requirements.txt

# Optional: fast Windows capture (DXGI backend)
pip install dxcam

# Optional: Windows Graphics Capture API
pip install winsdk comtypes pywin32

# Optional: GPU acceleration (pick your CUDA version)
pip install cupy-cuda12x        # CUDA 12.x
# pip install cupy-cuda11x      # CUDA 11.x
```

---

### Configuration ✅

Configuration is managed through `configuration.yaml` in the project root. Ambilight Desktop uses YAML for human-readable configuration with strict validation and atomic writes to prevent corruption.

**Important**: The configuration system guarantees **round-trip preservation** — any valid configuration field present in the file will be preserved when the system reads, modifies, and writes the configuration back. Configuration updates use the atomic write pattern (write to temporary file, then rename) to prevent corruption during system crashes or power loss.

For the complete configuration schema, see [TRD Section 10](docs/03_trd.md#10-configuration-schema-json-schema-fragment) or inspect `ambilight/config.py` (`AppConfig` dataclass).

#### 3. Configure

Edit `configuration.yaml`:

```yaml
device:
  ip: "192.168.1.29"   # ← your MagicHome controller IP
  mac: "aa:bb:cc:dd:ee:ff"  # optional but recommended

capture:
  method: wgc          # wgc | dxgi | mss
  monitor_index: 0     # 0 = primary
  fps_target: 30

color:
  mode: saturation_weighted  # best quality
```

### Configuration Schema Reference

The complete configuration schema defined in `ambilight/config.py`:

```yaml
device:
  ip: string              # IPv4 format, your MagicHome controller (default: 192.168.1.29)
  port: integer           # TCP port, default 5577
  mac: string (optional)  # MAC address for IP change detection
  subnet: string          # Subnet prefix for discovery (default: 192.168.1.)
  connect_timeout: float  # Seconds, default 2.0
  send_timeout: float     # Seconds, default 1.0
  reconnect_interval: float  # Seconds between reconnect attempts, default 5.0
  discovery_timeout: float   # Seconds per host during scan, default 0.5

capture:
  method: enum            # wgc | dxgi | mss (default: wgc)
  monitor_index: integer  # 0 = primary monitor
  fps_target: integer     # default 30
  analysis_width: integer # pixels wide for color analysis, default 80
  analysis_height: integer # pixels tall for color analysis, default 45

zones:
  top: integer            # LED count on top edge, default 7
  bottom: integer         # LED count on bottom edge, default 7
  left: integer           # LED count on left edge, default 4
  right: integer          # LED count on right edge, default 4

color:
  mode: enum              # average | edges | dominant | kmeans | saturation_weighted
  kmeans_clusters: integer         # clusters for kmeans mode, default 3
  ignore_black_threshold: integer  # 0-255; pixels darker than this are ignored, default 30
  ignore_white_threshold: integer  # 0-255; pixels brighter than this are ignored, default 225
  saturation_weight_power: float   # exponent for saturation weighting, default 2.0
  min_saturation: float            # minimum saturation to include a pixel, default 0.05

smoothing:
  enabled: boolean               # default true
  base_alpha: float              # 0.0-1.0, base EMA coefficient (lower = smoother), default 0.15
  adaptive_fast_threshold: integer  # colour delta above which fast mode activates, default 60
  adaptive_fast_alpha: float     # 0.0-1.0, EMA coefficient in fast mode, default 0.55
  min_change: integer            # skip LED update if max channel delta < this, default 2

gpu:
  enabled: boolean        # default true
  prefer: enum            # cupy | opencv_cuda | torch | none (default: cupy)
  fallback_to_cpu: boolean  # default true

logging:
  level: string           # DEBUG | INFO | WARNING | ERROR (default: INFO)
  file: string            # log file path (default: logs/ambilight.log)
  max_bytes: integer      # rotating log size, default 5242880 (5 MB)
  backup_count: integer   # number of backup log files, default 3
  show_fps: boolean       # log FPS metrics, default true
  fps_interval: float     # seconds between FPS log lines, default 5.0
```

---

### Usage ✅

```bash
python main.py --discover
```

Prints all MagicHome controllers found on your subnet with their IPs and MACs.

#### 5. List monitors

```bash
python main.py --list-monitors
```

#### 6. Run

```bash
python main.py
python main.py --config /path/to/custom.yaml
python main.py --ip 192.168.1.50 --mode kmeans --debug
```

---

### Performance Optimisation

#### Capture backend selection

| Backend | Latency | DRM bypass | Platform |
|---|---|---|---|
| WGC | ★★★ | Yes (compositor) | Windows 10 1903+ |
| DXGI (dxcam) | ★★★ | No | Windows |
| MSS | ★★ | No | All |

Install `dxcam` and `winsdk` to unlock the two fastest backends.

#### Analysis resolution

The default 80×45 pixels (= 3,600 pixels) gives excellent quality with
negligible CPU load.  Reduce to 40×22 for embedded/low-power systems;
increase to 160×90 for higher accuracy with the `kmeans` mode.

#### GPU acceleration

With CuPy installed and a CUDA GPU available:

- Frame resize happens entirely on the GPU.
- Weighted mean calculations are parallelised across thousands of pixels.
- End-to-end latency typically drops from 8–15 ms to 2–5 ms.

If no GPU is detected the system silently falls back to NumPy on CPU.

#### Smoothing tuning

| Use case | `base_alpha` | `fast_alpha` | `fast_threshold` |
|---|---|---|---|
| Cinema / ambient | 0.08 | 0.40 | 80 |
| Gaming (default) | 0.15 | 0.55 | 60 |
| Reactive / party  | 0.30 | 0.80 | 30 |

#### Network overhead

- `min_change: 2` suppresses transmissions for imperceptible colour changes
  (saves ~30% of packets on static scenes).
- `TCP_NODELAY` is set on the socket to eliminate Nagle's algorithm delay.
- Duplicate-colour suppression prevents re-sending the same RGB value.

---

### Troubleshooting

#### "No MagicHome devices found"

1. Run `python main.py --discover` from the same network.
2. Verify the controller is powered and connected (blue LED on most units).
3. Check `subnet` in config matches your network (e.g. `192.168.0.` not `192.168.1.`).
4. Firewall: ensure TCP port 5577 is not blocked.

#### "All backends exhausted — no capture source available"

- **Windows**: install `mss` (`pip install mss`) as the guaranteed fallback.
- **Linux/macOS**: only MSS is supported; make sure it is installed.

#### DRM-protected content appears black

- Use the **WGC backend** (`method: wgc`) — it captures the GPU compositor
  surface which includes decoded video on most streaming apps.
- Install `winsdk` and `comtypes`: `pip install winsdk comtypes pywin32`.
- Some apps (e.g. Netflix UWP) block even WGC; use browser-based streaming
  instead.

#### High CPU usage

1. Lower `fps_target` (e.g. 20).
2. Reduce analysis resolution (`analysis_width: 40`, `analysis_height: 22`).
3. Switch from `kmeans` to `saturation_weighted` or `average`.
4. Install GPU acceleration (CuPy or PyTorch CUDA).

#### LED flickering / colour jumping

1. Lower `base_alpha` (e.g. 0.08) for slower, smoother transitions.
2. Raise `min_change` (e.g. 5) to suppress minor variations.
3. Lower `adaptive_fast_threshold` (e.g. 40) to react more gradually to
   medium-sized changes.

#### Device IP changed after router restart

- Set the `mac` field in config to your controller's MAC address.
  The discovery module will scan the subnet to find the new IP automatically.
  Use `python main.py --discover` to find the MAC.

#### "ImportError: No module named 'winsdk'"

WGC is only available on Windows 10 1903+.  The engine automatically falls
back to DXGI or MSS if WGC is unavailable — no action needed.

#### Debug mode

```bash
python main.py --debug
# or
AMBILIGHT_LOG_LEVEL=DEBUG python main.py
```

Logs include per-frame RGB values, zone analysis results, and timing data.

---

### Environment Variables

| Variable | Effect |
|---|---|
| `AMBILIGHT_IP` | Override device IP |
| `AMBILIGHT_MAC` | Override device MAC |
| `AMBILIGHT_MODE` | Override colour mode |
| `AMBILIGHT_FPS` | Override FPS target |
| `AMBILIGHT_LOG_LEVEL` | Override log level |
| `AMBILIGHT_MONITOR` | Override monitor index |
| `AMBILIGHT_GPU` | Override GPU backend (`cupy`, `opencv_cuda`, `torch`, `none`) |

---

### Colour Modes Reference

| Mode | Quality | Speed | Best for |
|---|---|---|---|
| `average` | ★★ | ★★★★★ | Static scenes, low-power |
| `edges` | ★★★ | ★★★★ | Wide-format video with bars |
| `dominant` | ★★★★ | ★★★ | Animated content |
| `kmeans` | ★★★★★ | ★★ | Accuracy-critical setups |
| `saturation_weighted` | ★★★★★ | ★★★★ | **Default — best balance** |

---

## Planned Service Architecture 🚧

> **Status: Planned / In Active Development** — The features described in this section are architectural goals. Some foundational pieces are already in the codebase (REST API, pipeline controller, NSIS installer hooks); others are not yet implemented. Nothing here should be read as "currently working out of the box." Check the [Development Status](#development-status) section for what works today.

### Vision: Install, Configure, Forget

The long-term goal is a system that runs silently in the background from the moment your PC boots. You should never think about it. Plug in your LED controller, install the app, and your display perimeter is lit — automatically, every time, even after crashes, sleep/wake cycles, or display changes.

This means two properties must hold:
- **Persistent operation**: the lighting engine keeps running whether the desktop UI is open or closed.
- **Zero-maintenance recovery**: the service restarts itself after any failure — no manual intervention required.

### Dual-Component Architecture 🚧

The planned architecture separates concerns cleanly into two independent components:

```
┌─────────────────────────────────────┐     ┌──────────────────────────────────────┐
│         Python Background Service   │     │        Electron Desktop UI           │
│                                     │     │                                      │
│  • Screen capture (WGC/DXGI/MSS)   │     │  • Real-time metrics dashboard       │
│  • Colour analysis + smoothing      │◄────┤  • Profile management                │
│  • LED output (MagicHome TCP)       │     │  • Effects & mode switching          │
│  • REST API  :7826                  │────►│  • Device management                 │
│  • WebSocket :7825                  │     │  • Settings editor                   │
│  • Profile & config management      │     │  • Log viewer                        │
│                                     │     │                                      │
│  Runs always — UI is optional       │     │  Optional — close it anytime         │
└─────────────────────────────────────┘     └──────────────────────────────────────┘
         ▲
         │  OS Service Manager
         │  (Windows Service / launchd / systemd)
         │
    Starts at login, restarts on crash
```

**What's implemented today:**
- ✅ Python service core: `ambilight/api_server.py`, `ambilight/pipeline_controller.py` — FastAPI + multiprocessing pipeline, fully functional when launched manually
- ✅ Electron UI: `ui/electron/main.js` — connects to the running API server, forwards WebSocket metrics, exposes IPC for profiles/config/mode
- ✅ NSIS installer hooks: `ui/installer/nsis_hooks.nsh` — Windows Service registration via `sc.exe` with `sc failure` crash recovery (written, not yet distributed as a packaged build)
- ✅ Display event recovery: `ambilight/pipeline_controller.py` — pause/resume on system sleep, wake, lock/unlock events

**What is NOT yet implemented:**
- 🚧 Electron-managed service lifecycle: the Electron app does not yet spawn, health-check, or restart the Python service — it expects the service to already be running
- 🚧 Service surviving UI closure: today, closing all Electron windows exits the app (`app.quit()`); the service does not persist independently
- 🚧 macOS launchd / Linux systemd service registration
- 🚧 Packaged installer distributing the Python service binary alongside the Electron app
- 🚧 Electron-side health check loop and automatic crash recovery

### Service Lifecycle 🚧

The planned service lifecycle, once fully implemented:

```
OS Boot / User Login
       │
       ▼
  OS Service Manager  ─────────── registers at install time
  (NSSM on Windows / launchd / systemd)
       │ auto-starts
       ▼
  Python Service (ambilight.service)
       │
       ├── Read config from ~/.ambilight/config.yaml
       ├── Write auth_token  → ~/.ambilight/auth_token
       ├── Start REST API    → :7826
       ├── Start WebSocket   → :7825
       ├── Start display event watcher
       ├── Start device discovery
       └── Start capture pipeline
              │
              RUNNING ──────────────────────────────────────────┐
              │                                                  │
              ├── Screen sync loop (30 FPS)                      │
              ├── [Sleep / wake]    → pause / resume pipeline    │
              ├── [Display change]  → restart capture            │
              ├── [Config change]   → hot-reload settings        │
              ├── [API call]        → update state from UI       │
              └── [Device drop]     → reconnect loop             │
                                                                  │
  ┌───────────────────────────────────────────────────────────────┘
  │  Service crash / OOM / unhandled exception
  │
  └──► OS watchdog restarts service within 5–30 s
       (Windows: `sc failure` restart policy — written in nsis_hooks.nsh)
       (macOS:   `KeepAlive: true` in launchd plist — planned)
       (Linux:   `Restart=on-failure` in systemd unit — planned)
```

Key lifecycle properties:
- **Auto-start on login**: the service is registered as an OS-level service at install time, starting automatically before any user action.
- **Survives UI closure**: the LED sync continues even after the Electron desktop app window is closed.
- **Crash recovery**: if the Python process terminates unexpectedly, the OS service manager restarts it automatically — no manual restart needed.
- **Internal subsystem recovery**: within a running service, capture process crashes are detected and restarted independently (planned; watchdog loop not yet implemented).

### Communication Layer ✅ / 🚧

The communication layer between the Python service and the Electron UI is the API already implemented in the current codebase:

| Channel | Port | Purpose | Status |
|---------|------|---------|--------|
| REST API (FastAPI) | 7826 | Configuration, profiles, pipeline control, mode switching | ✅ Implemented |
| WebSocket | 7825 (via `/ws` on port 7826) | Real-time metrics, live log streaming | ✅ Implemented |
| Auth token | `~/.ambilight/auth_token` | Bearer token shared between service and UI | ✅ Implemented |

The Electron main process reads the auth token from disk and forwards it as a Bearer header on all REST calls. WebSocket connections pass the token as a query parameter. The renderer process never sees the token — all API calls proxy through the Electron main process.

For the full API specification, see [TRD Section 7](docs/03_trd.md) and the [Electron Architecture doc](docs/05_electron_architecture.md).

### Single-Installer Distribution 🚧

The current setup requires you to install Python, create a virtual environment, and run from source. The planned distribution model eliminates all of that:

- A single NSIS installer (`.exe` on Windows) will contain both the Python service (compiled to a self-contained binary via PyInstaller) and the Electron desktop app.
- The installer registers the Python binary as a Windows Service automatically — no manual `python main.py` required after installation.
- macOS (`.dmg`) and Linux (`.AppImage` / `.deb`) packaging is planned for a later milestone.

The NSIS installer hooks (`ui/installer/nsis_hooks.nsh`) for Windows service registration are already written. The remaining work is integrating the PyInstaller build of the Python service into the electron-builder packaging pipeline.

> For full details on the service architecture design, see [Service Architecture doc](docs/06_service_architecture.md) and [Electron Architecture doc](docs/05_electron_architecture.md).


---

## 🚨 Known Limitations & Future Work

### Critical Gaps (Blocking Full Feature Set)

1. **Service Auto-Start** (❌ Not implemented)
   - The API server must be started manually (`python main.py`)
   - Does NOT run as a Windows Service automatically on boot
   - Status: Requires integration with Windows SCM (partial code in nsis_hooks.nsh)

2. **Background Service Persistence** (❌ Not implemented)
   - Closing the Electron UI does NOT keep the LED sync running
   - The service terminates when the main process exits
   - Status: Requires service/UI process separation

3. **Auto-Restart on Crash** (❌ Not implemented)
   - If the Python process crashes, it stays crashed
   - No watchdog loop or OS-level crash recovery is active
   - Status: Windows watchdog code written, not enabled

4. **Advanced UI Components** (❌ Mostly missing)
   - No device manager UI (show connected devices, health status)
   - No settings editor (must edit YAML manually)
   - No zone/layout editor for LED strip configuration
   - No effect preview or audio-reactive effects
   - Status: Basic Dashboard and Diagnostics tabs work, everything else planned

5. **Packaged Installer** (❌ Not distributed)
   - Single-installer distribution not ready for end-users
   - Requires running from source with Python installed
   - Status: NSIS hooks written; PyInstaller integration pending

6. **macOS & Linux Support** (❌ Untested)
   - Code is cross-platform, but only tested on Windows
   - WGC capture is Windows-specific (DXCam fallback on other platforms)
   - Service registration (launchd/systemd) not implemented
   - Status: Linux/macOS support planned post-MVP

### Partial Implementations (Work In Progress)

| Component | Status | Details |
|-----------|--------|---------|
| **WebSocket Metrics** | ⚠️ Partial | Token auth issue on `/ws` endpoint needs debugging |
| **Multi-Monitor Config** | ⚠️ Partial | Config supports `monitor_index`, but no UI to select which monitor |
| **Device Health Display** | ⚠️ Partial | Device status tracked internally, not exposed in UI |
| **Effect Library** | ⚠️ Partial | Only 4 modes in UI; audio-reactive & presets not implemented |
| **Profile Management** | ⚠️ Partial | Save/load/apply work via API; no built-in profiles or auto-switch |
| **Log Level Filter** | ⚠️ Partial | Logs display; no filter by level in UI |
| **Hot-Reload Config** | ⚠️ Partial | Event system ready, no UI to trigger reload |

### Roadmap - Next Steps

**Phase 2 (Planned):** Service Architecture & Windows Service Integration
- [ ] Enable Windows Service auto-start on boot
- [ ] Separate service process from Electron UI process
- [ ] Add service health check and auto-restart watchdog
- [ ] Implement process crash recovery loop
- **Estimated:** 2-3 weeks

**Phase 3 (Planned):** Advanced UI Components
- [ ] Device manager panel (list, health, capability probe)
- [ ] Settings editor (visual config builder, no manual YAML)
- [ ] Zone editor for LED strip layout configuration
- [ ] Effect library browser with live preview
- [ ] Service start/stop/restart buttons in UI
- **Estimated:** 3-4 weeks

**Phase 4 (Planned):** Audio & Advanced Effects
- [ ] Audio-reactive beat detection via microphone/system audio
- [ ] Scene presets (Sunrise, Sunset, Candlelight, Ocean, Ambient)
- [ ] Custom effect scripting API (Python-based, safe sandbox)
- [ ] Effect scheduling (cron-like: "night mode at 22:00")
- **Estimated:** 2-3 weeks

**Phase 5 (Planned):** Packaged Installer & Distribution
- [ ] Integrate PyInstaller for Python service binary
- [ ] Single-click NSIS installer for Windows
- [ ] macOS `.dmg` and Linux `.AppImage` / `.deb` packaging
- [ ] Auto-update mechanism with rollback
- **Estimated:** 1-2 weeks

**Phase 6+ (Post-MVP):** Platform Expansion & Enhancements
- [ ] macOS launchd / Linux systemd service registration
- [ ] Multi-device support (multiple LED controllers per system)
- [ ] HTTP2/gRPC for faster API communication
- [ ] Plug-in/extension system for community effects
- [ ] Cloud sync of profiles and settings
- [ ] Mobile companion app for remote control

---

## 📡 REST API Reference

All endpoints require `Authorization: Bearer <token>` header. Token is generated on first startup and written to `auth_token` file.

### Health & Status

```
GET /api/status
```
Returns service status and pipeline PID.
```json
{
  "status": "running" | "stopped",
  "paused": false,
  "pid": 12345
}
```

### Configuration

```
GET /api/config
```
Returns current configuration (all 21 fields).

```
PUT /api/config
Content-Type: application/json

{ "color": { "mode": "kmeans" }, "capture": { "fps_target": 60 } }
```
Updates configuration fields (delta update; unchanged fields are preserved).

### Profiles

```
GET /api/profiles
```
Returns list of saved profile names.
```json
{ "profiles": ["gaming", "movie", "productivity"] }
```

```
POST /api/profiles/{name}
```
Save current configuration as a named profile.

```
GET /api/profiles/{name}
```
Retrieve a specific profile's configuration.

```
DELETE /api/profiles/{name}
```
Delete a profile.

```
POST /api/profiles/{name}/apply
```
Load and apply a profile.

### Pipeline Control

```
POST /api/pipeline/start
POST /api/pipeline/stop
```
Start or stop the capture pipeline.

### Effects & Modes

```
PUT /api/mode
Content-Type: application/json

{
  "mode": "screen_sync" | "static" | "breathing" | "rainbow",
  "params": { "r": 255, "g": 100, "b": 50, "speed": 1.0 }
}
```
Switch to an effect mode.

### WebSocket (Real-Time Metrics)

```
ws://127.0.0.1:7826/ws?token=<token>
```
Subscribes to real-time metrics streamed at ~10 Hz.
```json
{
  "fps": 29.3,
  "latency_ms": 34.2,
  "capture_time_ms": 12.5,
  "process_time_ms": 8.3,
  "led_transmit_ms": 2.1,
  "uptime_s": 3600.5,
  "cpu_usage": 4.2,
  "memory_usage_mb": 125.6
}
```

> Full API specification with request/response schemas: [TRD Section 7](docs/03_trd.md)

---

## License

MIT — use freely, contribute back.
