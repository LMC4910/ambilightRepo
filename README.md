# Ambilight Desktop

**Cross-platform ambient lighting platform that works the way it should — install, configure, forget.**

[![Build Status](https://github.com/LMC4910/ambilightRepo/actions/workflows/build.yml/badge.svg)](https://github.com/LMC4910/ambilightRepo/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Windows](https://img.shields.io/badge/Windows-Officially%20Supported-success)](docs/platform__support.md)
[![Linux](https://img.shields.io/badge/Linux-Officially%20Supported-success)](docs/platform__support.md)
[![macOS](https://img.shields.io/badge/macOS-Builds%20Pending%20Signing-warning)](docs/platform__support.md)

> **Transform any display into an immersive viewing experience with dynamic, screen-reactive LED lighting — without proprietary hardware lock-in.**

**Ambilight Desktop** is a production-grade ambient lighting platform that extends any display with dynamic, screen-reactive LED lighting. It delivers a premium Philips Ambilight experience on custom hardware — without proprietary lock-in.

It ships as a **persistent Python background service** plus a **native Electron control app**, built into **single-file installers** (Windows NSIS, macOS DMG, Linux AppImage/deb) with code-signing and auto-update wired in (active once you supply certs + a release feed). The desktop app spawns, supervises, and crash-restarts the service; the service keeps your LEDs synced whether the window is open, minimised to the tray, or closed. The original `python main.py` CLI remains available for source/headless use.

## Development Status

_Last updated: 2026-06-04_

The MVP (P0), the v1.1 feature set (P1), and most of the v1.2 (P2) scope are **implemented and verified on Windows**. The product installs, self-supervises, recovers, and persists configuration without manual intervention.

| Area | Status |
|------|--------|
| **Background service** (`python -m ambilight.service`) — FastAPI REST + WebSocket on `127.0.0.1:7826` | ✅ Done |
| **Electron desktop app** — spawns/supervises the service, tray, onboarding, dashboards | ✅ Done |
| **Service survives UI close** (minimise-to-tray) + **auto-start on login** | ✅ Done |
| **Crash recovery** — Electron watchdog + in-service pipeline-worker watchdog (≤10 s) | ✅ Done |
| **Display-event recovery** (sleep/wake/lock, monitor connect/disconnect) | ✅ Done |
| **Packaged installers** (PyInstaller service + electron-builder) with **code-sign config** + **electron-updater** (GitHub Releases) | ✅ Done (unsigned until certs supplied) |
| **Multi-device + multi-monitor**, gradient engine, profiles + built-ins, diagnostics, log viewer | ✅ Done |
| **Per-user config/profile persistence** under `~/.ambilight` | ✅ Done |
| **Audio-reactive mode** (system-audio loopback) + **scene presets** (sunrise/sunset/ocean/ambient) | ✅ Done |
| **Functional WGC capture** (catches hardware-overlay video DXGI misses; hardware DRM still excluded by Windows) | ✅ Done |
| **Visual zone-layout editor** (per-edge counts + thickness, live preview, hot-reload) | ✅ Done |
| **Web dashboard** | 🚧 Not yet |

**Distribution prerequisites you must supply:** real code-signing certificates (Windows `.pfx`, Apple Developer ID) and a GitHub repo + `GH_TOKEN` before signed builds and end-to-end auto-update work. Without them, installers build **unsigned** (Windows SmartScreen warning; macOS auto-update inactive).

See [Feature Implementation Status](#-feature-implementation-status) for the per-feature breakdown and [Roadmap](#roadmap) for what's next.

---

## ✨ Feature Implementation Status

### ✅ What Works Today

#### Background service (Python / FastAPI)
| Component | Status | Details |
|-----------|--------|---------|
| **Service entry** | ✅ | `python -m ambilight.service` (long-lived); legacy `python main.py` kept for source/headless use |
| **REST API + WebSocket** | ✅ | `127.0.0.1:7826`, Bearer-token auth; WS metrics on `/ws` (~10 Hz) |
| **Screen capture** | ✅ | WGC → DXGI/DXCam → MSS auto-failover, 24–30 FPS, <50 ms latency |
| **Colour analysis** | ✅ | 5 modes: average, edges, dominant, kmeans, saturation_weighted; per-zone |
| **Gradient engine** | ✅ | linear / radial / ambient / screen_matched + gamma; addressable `set_pixels` path |
| **Effects engine** | ✅ | screen_sync, static, breathing, rainbow, candle, **sunrise/sunset/ocean/ambient** scenes, **audio-reactive** (loopback) + **scheduler** (time windows) + **plugin loader** (`~/.ambilight/plugins`) |
| **Multi-device + multi-monitor** | ✅ | One capture per monitor shared across per-device channels |
| **Device discovery / reconnect** | ✅ | MAC-based discovery, capability probe, exponential reconnect backoff |
| **Config** | ✅ | YAML + env overrides + **hot-reload** (file watcher); persisted to `~/.ambilight/configuration.yaml` |
| **Profiles** | ✅ | save/load/apply/delete/import/export + built-ins (Gaming, Movie, Night) |
| **Auto profile switching** | ✅ | Foreground-app → profile rules (FR-PROF-07), with a default fallback; applied live |
| **Crash + display recovery** | ✅ | pipeline-worker watchdog (≤10 s); pause/resume on sleep/wake/lock; rebuild on monitor change |
| **Auth / logging** | ✅ | per-session Bearer token (0600); rotating logs, split console/file levels, captured service stdio |

#### Desktop app (Electron / React)
| Component | Status | Details |
|-----------|--------|---------|
| **Service supervision** | ✅ | Spawns, health-checks, and crash-restarts the bundled service; adopts an already-running one |
| **System tray + minimise-to-tray** | ✅ | LEDs keep running with the window closed; tray start/stop/restart + update check |
| **First-run onboarding wizard** | ✅ | Monitor → device → test → profile → auto-start |
| **Dashboard / Diagnostics / Logs** | ✅ | Live FPS/latency/uptime, zone preview, SVG charts, log viewer (with level filter) |
| **Devices / Profiles / Settings** | ✅ | Multi-device setup with monitor assignment, profile import/export, full settings editor |
| **Zone-layout editor** | ✅ | Visual per-edge LED counts + strip thickness, live-tinted preview, hot-reloads the running pipeline |
| **Auto-start toggle + updates** | ✅ | "Start on login"; electron-updater banner + "Check for updates" |
| **Auto-update** | ✅ wired | electron-updater via GitHub Releases (dormant until a release feed + repo exist) |

#### Packaging & distribution
| Component | Status | Details |
|-----------|--------|---------|
| **Service binary** | ✅ | PyInstaller one-dir bundle (`build.py`) shipped under `resources/service` |
| **Installers** | ✅ | NSIS (Windows), DMG (macOS), AppImage/deb (Linux) via electron-builder |
| **Branded icons** | ✅ | Generated from the brand SVG (`scripts/gen-icons.mjs`) |
| **Code signing / notarization** | ✅ config | Env-driven (Windows `.pfx`, Apple Developer ID) — **inert until you supply certs** |
| **Release CI** | ✅ | Tag-triggered 3-OS build + publish workflow |

### 🚧 Not Yet Implemented

| Feature | Ref | Notes |
|---------|-----|-------|
| Hardware-DRM capture | FR-CAP-05 | WGC capture **is** implemented, but HDCP/PlayReady fullscreen video is excluded by Windows — no API bypasses it |
| Web dashboard | P2 | Intentionally not built — this is a native app, not a web portal |

### 🎯 Non-Functional Requirements Status

| Requirement | Target | Status |
|---|---|---|
| End-to-end latency | ≤ 50 ms | ✅ ~34–47 ms |
| Capture FPS | ≥ 24 | ✅ ~29 FPS (screen_sync) |
| Crash recovery | ≤ 10 s | ✅ watchdog verified |
| Config/profile persistence | survive restart | ✅ `~/.ambilight` |
| Windows support | full | ✅ verified (capture, service, installer) |
| macOS / Linux | full | 🚧 builds configured; lightly tested, MSS-only capture |
| CPU ≤ 5% / Memory ≤ 150 MB / MTBF ≥ 7 days | — | ⏳ not yet profiled long-term |

### 📋 Verification highlights (2026-06-04)
- `pytest` — **56/56 passing**.
- Installed/packaged app on Windows: service spawns from `resources/service`, `/health` green, two service processes (API + pipeline worker), survives window close.
- Installer build produces `Ambilight Desktop Setup 1.0.0.exe` + `latest.yml` (updater feed).
- First run seeds `~/.ambilight/configuration.yaml` + built-in profiles; UI config edits persist back to that file.

---

## Who Is This For?

Ambilight Desktop serves four distinct user types. Find yours and jump straight to what matters.

| Persona | Core Need | Jump To |
|---|---|---|
| 🎬 Home Theater Enthusiast | overlay-video capture, cinema smoothing, sleep/wake recovery | [Quick Start](#quick-start) · [Capture Backends](#capture-backend-selection) · [Smoothing](#smoothing-tuning) |
| 🎮 PC Gamer | <50 ms latency, zero FPS impact, gaming profiles | [Quick Start](#quick-start) · [Performance](#performance-optimisation) · [Colour Modes](#colour-modes-reference) |
| 💻 Developer / Power User | REST API, WebSocket metrics, profile CRUD, scriptable modes | [API Server](#architecture-) · [Environment Variables](#environment-variables) · [Contributing](#contributing) |
| 👤 Casual User | Simple setup, auto-discovery, graphical UI | [Quick Start](#quick-start) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting) |

### 🎬 Home Theater Enthusiast

You watch Netflix, Disney+, or local media daily on a display ringed with LED strips. You want cinema-quality smoothing so scene cuts don't produce jarring LED jumps, and automatic recovery — the display event handler in `pipeline_controller.py` pauses and resumes on sleep, wake, and lock with no manual restarts. The default **WGC** backend captures the composited desktop, so hardware-accelerated video (players/browsers) that DXGI renders black now lights up correctly. _Note: true hardware-DRM fullscreen (Netflix app, PlayReady) is excluded by Windows and stays black under any capture API — see [Troubleshooting](#video-appears-black)._

→ [Quick Start](#quick-start) · [Capture Backend Selection](#capture-backend-selection) · [Smoothing Tuning](#smoothing-tuning) · [DRM Troubleshooting](#video-appears-black)

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
- [Architecture & Components ✅](#architecture--components-)
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
- [Service Architecture ✅](#service-architecture-)
  - [Building Installers](#building-installers)
- [REST API Reference](#-rest-api-reference)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

### Option A — Install the desktop app (recommended)

1. Build (or download) the installer for your OS — see [Building Installers](#building-installers). On Windows you get `ui/release/Ambilight Desktop Setup <version>.exe`.
2. Run the installer and launch **Ambilight Desktop**.
3. The app starts the background service automatically and walks you through the first-run wizard (pick a monitor, discover your controller, test it, optionally enable start-on-login).

The service then runs whenever you're logged in — minimise the window to the tray and forget about it.

### Option B — Run from source (service / CLI)

```bash
# 1. Install Python 3.12 (3.10+ works) and clone the project
cd ambilightRepo

# 2. Create a venv and install dependencies
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 3. Discover your MagicHome controller, then set its IP in configuration.yaml
python main.py --discover

# 4a. Run the long-lived background service (REST + WebSocket on :7826)
python -m ambilight.service

# 4b. …or the original one-shot CLI pipeline
python main.py
```

To run the Electron UI against a source checkout: `cd ui && pnpm install && pnpm run dev` (it will spawn the service from your `.venv` automatically).

---

## Architecture & Components ✅

**Status: implemented and verified on Windows.**

Ambilight Desktop runs as two cooperating components that share one production-ready pipeline core:

- ✅ **Background service** — `python -m ambilight.service` (or the bundled `ambilight-service` binary). FastAPI REST + WebSocket on `127.0.0.1:7826`, token-secured, with the capture pipeline isolated in a `multiprocessing` worker under a crash watchdog.
- ✅ **Electron desktop app** — spawns/supervises the service, system tray, onboarding, and full settings/diagnostics UI.
- ✅ **CLI** — the original `python main.py` for one-shot/headless runs and `--discover` / `--list-monitors` utilities.

#### Entry points

**Background service (`python -m ambilight.service`)**  
The long-lived entry the desktop app and installers launch. Loads config (from `~/.ambilight/configuration.yaml` in installed builds), starts uvicorn, the platform monitor, the config watcher, and the pipeline controller. Flags: `--config`, `--host`, `--port` (env: `AMBILIGHT_CONFIG/HOST/PORT`).

**REST API + WebSocket (port 7826)**  
Configuration, profiles, devices, diagnostics, effects, autostart, and pipeline control. WebSocket at `/ws` streams metrics at ~10 Hz. All endpoints secured with a per-session Bearer token written 0600 by `auth.py`. See the [REST API Reference](#-rest-api-reference).

**Desktop app (Electron UI)**  
Spawns and health-checks the service, forwards WS metrics, and proxies all REST calls (the renderer never sees the token). Provides dashboard, devices, profiles, settings, logs, diagnostics, tray, onboarding, and auto-update.

**CLI (`python main.py`)**  
One-shot pipeline plus `--discover`, `--list-monitors`, `--ip`, `--mode`, `--debug`.

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
capture.py                                    screen_sync | static | breathing
                                               rainbow | candle (+ scheduler,
                                               plugins)
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
  service/__main__.py Long-lived service entry (uvicorn boot, config seeding)
  config.py           YAML config → typed AppConfig dataclass (atomic save)
  config_watcher.py   Watch configuration.yaml → hot-reload (CONFIG_UPDATE)
  paths.py            ~/.ambilight data dir + bundled-resource resolution
  discovery.py        Subnet scanner + MAC-based device cache + capability probe
  logging_setup.py    Rotating logs (split console/file levels) + metrics thread
  auth.py             Per-session Bearer token; 0600 file permissions
  profile_manager.py  Save / load / apply / import / export profiles + built-ins
  autostart.py        Start-on-login (Win Startup / launchd / systemd)
  events.py           Async EventBus (subscribe/publish pattern)
  platform_monitor.py OS sleep/wake/lock + monitor change → EventBus
  gradient_engine.py  linear / radial / ambient / screen_matched + gamma
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
| `effects_engine.py` | Non-capture effects (`static`, `breathing`, `rainbow`, `candle`) + time-window scheduler + plugin loader |
| `profile_manager.py` | Save/load/list/apply/delete/import/export profiles; seeds built-ins; user-dir aware |
| `discovery.py` | Parallel TCP scan; MAC-based caching; reconnect after IP change; capability probe |
| `led_output.py` | MagicHome TCP protocol; rate limiting; duplicate suppression; reconnect; `set_pixels` |
| `config.py` | Load/validate YAML config; typed `AppConfig`; atomic save back to the loaded path |
| `config_watcher.py` | Watch `configuration.yaml` (watchdog or mtime polling) → emit `CONFIG_UPDATE` |
| `paths.py` | Resolve `~/.ambilight` data dir and bundled resources (frozen vs source) |
| `service/__main__.py` | `python -m ambilight.service` entry: config seeding, uvicorn boot |
| `autostart.py` | Start-on-login: Windows Startup launcher / macOS launchd / Linux systemd |
| `logging_setup.py` | Rotating file + console logging (independent levels); FPS/latency metrics thread |
| `gradient_engine.py` | linear / radial / ambient / screen_matched gradients with gamma correction |

### Features ✅

- ✅ **Self-supervising service**: Electron spawns, health-checks, and crash-restarts the background service; it survives window close (minimise-to-tray) and can start on login.
- ✅ **Multi-backend screen capture**: WGC (default — captures hardware-overlay video), DXGI, MSS with automatic failover.
- ✅ **Multi-device + multi-monitor**: one capture per monitor shared across per-device channels, each with its own LED count/zones.
- ✅ **5 colour analysis modes**: average, edges, dominant, k-means, saturation-weighted (per-zone).
- ✅ **Gradient engine**: linear / radial / ambient / screen_matched with gamma; addressable-strip output.
- ✅ **GPU acceleration**: CuPy, OpenCV CUDA, PyTorch with automatic CPU fallback.
- ✅ **Adaptive smoothing**: per-zone EMA, fast on scene cuts, gentle on subtle changes.
- ✅ **Auto device discovery**: parallel subnet scan, MAC-based caching, capability probe, reconnect after IP change.
- ✅ **Effects engine**: screen_sync, static, breathing, rainbow, candle, sunrise/sunset/ocean/ambient scenes, and **audio-reactive** (system-audio loopback) + time-window scheduler + drop-in plugins.
- ✅ **Profiles**: save/load/apply/import/export + built-in Gaming / Movie / Night, plus **auto-switch by foreground app**.
- ✅ **Desktop UI**: tray, first-run wizard, dashboard, diagnostics, log viewer, settings editor, device manager, live zone preview, auto-update.
- ✅ **Packaging**: signed-installer config + electron-updater + PyInstaller service bundle + release CI.
- ✅ **Performance**: ~30 FPS, <50 ms end-to-end latency; GPU path reduces frame processing to 2–15 ms.

### Platform Support ✅

| Platform | Status | Capture Backends | Min Version | Notes |
|----------|--------|------------------|-------------|-------|
| Windows 10 | ✅ Primary | WGC, DXGI, MSS | 1903 (build 18362) | WGC requires 1903+; 22H2+ recommended |
| Windows 11 | ✅ Primary | WGC, DXGI, MSS | 23H2 | Recommended platform |
| macOS | 🚧 Experimental | MSS only | 13 Ventura | WGC/DXGI unavailable; GPU acceleration not supported; ScreenCaptureKit planned |
| Linux | 🚧 Experimental | MSS only | Ubuntu 22.04 LTS | WGC/DXGI unavailable; GPU acceleration not supported; PipeWire planned |

> **Experimental platforms** (macOS, Linux): The core pipeline runs and MSS capture works, but these platforms receive limited testing and no hardware-accelerated capture. Expect reduced performance and potential rough edges. Contributions welcome.

**Capture Backend Comparison:**

| Backend | Latency | Overlay video | Hardware DRM | Platform | Requirements |
|---------|---------|---------------|--------------|----------|--------------|
| WGC | ★★★ | ✅ Yes (composited) | ❌ No (OS-excluded) | Windows 10 1903+ | `pip install windows-capture` |
| DXGI (dxcam) | ★★★ | ⚠️ Misses some | ❌ No | Windows | `pip install dxcam` |
| MSS | ★★ | ⚠️ Misses some | ❌ No | Windows, macOS, Linux | Included in `requirements.txt` |

The capture manager tries backends in priority order (WGC → DXGI → MSS) and automatically fails over if a backend is unavailable. On macOS and Linux, only MSS is attempted.

> ✅ **WGC status:** the Windows Graphics Capture backend is **functional** (via the native `windows-capture` package) and is the default. Because it captures the DWM-composited desktop, it picks up **hardware-accelerated video overlay/MPO planes** that DXGI Desktop Duplication renders black. It does **not** defeat hardware DRM — HDCP/PlayReady-protected fullscreen video (e.g. the Netflix app) is excluded by Windows and stays black under every capture backend.

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

# Windows Graphics Capture (WGC) — default backend, captures overlay video.
# Installed by requirements.txt on Windows; install explicitly if needed:
pip install windows-capture

# Optional: DXGI Desktop Duplication fallback backend
pip install dxcam

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
  edge_fraction: float    # edge-strip thickness as a fraction of frame H/W, default 0.25

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

gradient:
  enabled: boolean        # use addressable gradient output when supported, default true
  mode: enum              # linear | radial | ambient | screen_matched (default)
  gamma: float            # gradient gamma correction, default 2.2

effects:
  plugins_dir: string     # default resolves to ~/.ambilight/plugins
  schedule: list          # [{effect, params, window: "22:00-07:00"}]

auto_profile:             # auto-switch profile by foreground app (FR-PROF-07)
  enabled: boolean        # default false
  poll_interval: float    # seconds between foreground checks, default 2.0
  default_profile: string # applied when no rule matches ("" = leave unchanged)
  rules: list             # ordered, first match wins: [{match: "game.exe", profile: "gaming"}]

logging:
  level: string           # console level: DEBUG | INFO | WARNING | ERROR (default: INFO)
  file_level: string      # on-disk level, independent of console (default: INFO)
  file: string            # log file path (default: logs/ambilight.log, anchored under ~/.ambilight)
  max_bytes: integer      # rotating log size, default 20971520 (20 MB)
  backup_count: integer   # number of backup log files, default 10 (~220 MB ceiling)
  show_fps: boolean       # log FPS metrics, default true
  fps_interval: float     # seconds between FPS log lines, default 5.0
```

> **Multi-device:** add a `devices:` list (each entry a device block with `ip`, `mac`, `monitor_index`, `led_count`, `name`, `enabled`) to drive several controllers at once. When omitted, the single `device:` + `capture.monitor_index` is used. The `device:` block also accepts `led_count`, `monitor_index`, `name`, and `enabled`.
>
> **Installed builds** read and write `~/.ambilight/configuration.yaml` (seeded from the bundled default on first run); the repo `configuration.yaml` is the default template.

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

| Backend | Latency | Overlay video | Platform |
|---|---|---|---|
| WGC | ★★★ | Yes (composited; not hardware DRM) | Windows 10 1903+ |
| DXGI (dxcam) | ★★★ | No | Windows |
| MSS | ★★ | No | All |

Install `windows-capture` (WGC, default) and `dxcam` (DXGI) to unlock the two fastest backends. WGC is preferred because it also captures hardware-overlay video that DXGI misses.

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

#### Video appears black

- First, make sure the **WGC** backend is active (`capture.method: wgc`, the
  default). WGC captures the composited desktop and fixes most "black video"
  cases — hardware-accelerated **overlay/MPO planes** (many media players and
  hardware-accelerated browser video) that the DXGI backend renders black.
- **Hardware DRM is a hard limit:** HDCP/PlayReady-protected fullscreen video
  (e.g. the Netflix app, Edge/Chrome DRM playback) is excluded by Windows at the
  compositor level and stays black under **every** capture backend, including
  WGC. No documented API bypasses this — it's the purpose of the DRM.
- Workaround: use a player/source without hardware DRM, or windowed playback
  that the OS still composites normally.

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

#### WGC backend not active

WGC needs the `windows-capture` package (`pip install windows-capture`) and
Windows 10 1903+. If it's missing or unavailable the engine automatically falls
back to DXGI or MSS — no action needed, but you'll lose hardware-overlay video
capture. Check the log for `[Capture] Active backend: …`.

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

## Service Architecture ✅

> **Status: implemented and verified on Windows.** Install, configure, forget — the service runs whenever you're logged in, survives the UI window closing, and restarts itself after a crash. macOS/Linux builds are configured but lightly tested.

### Two cooperating components

```
┌─────────────────────────────────────┐     ┌──────────────────────────────────────┐
│        Python Background Service    │     │        Electron Desktop App          │
│                                     │     │                                      │
│  • Screen capture (WGC/DXGI/MSS)    │     │  • Spawns & supervises the service   │
│  • Colour analysis + smoothing      │◄────┤  • Tray + minimise-to-tray           │
│  • LED output (MagicHome TCP)       │     │  • Onboarding, dashboard, diagnostics│
│  • REST API + WebSocket  :7826      │────►│  • Profiles / devices / settings     │
│  • Profile & config management      │     │  • Auto-update prompts               │
│                                     │     │                                      │
│  Runs in the user session          │     │  Minimise to tray — keeps running    │
└─────────────────────────────────────┘     └──────────────────────────────────────┘
         ▲                                            │
         │ start-on-login launcher (autostart.py)     │ spawn + health-check + restart
         │ Win Startup / launchd / systemd            │ (Electron watchdog)
         └────────────────────────────────────────────┘
```

**Lifecycle model (why no Windows Service):** a screen-capture process must run inside the *interactive user session* — a Session-0 SYSTEM service can't see the desktop/GPU output. So the service is **not** installed as a Windows Service. Instead:

- The **Electron app spawns and supervises** the bundled service (`resources/service/ambilight-service`), health-checks `/health`, captures its stdout/stderr to `~/.ambilight/logs/service.out.log`, and **restarts it if it dies**. If a service is already healthy, it adopts it instead of double-spawning.
- **Start-on-login** is registered per-user (no admin) by `ambilight/autostart.py` — a Startup launcher on Windows, a launchd agent on macOS, a systemd user unit on Linux — toggled from Settings / onboarding.
- **Survives UI close** via minimise-to-tray; only an explicit Quit exits.
- **Two-level crash recovery:** the Electron watchdog respawns the whole service process; inside the service, the capture pipeline runs in a `multiprocessing` worker that `pipeline_controller.py` restarts within ≤10 s.
- **Display + device recovery:** pause/resume on sleep/wake/lock, rebuild capture on monitor connect/disconnect, reconnect to controllers with exponential backoff.

### Communication layer

| Channel | Endpoint | Purpose |
|---------|----------|---------|
| REST API (FastAPI) | `http://127.0.0.1:7826` | Config, profiles, devices, diagnostics, effects, autostart, pipeline control |
| WebSocket | `ws://127.0.0.1:7826/ws?token=…` | Real-time metrics (~10 Hz) |
| Auth token | `~/.ambilight/auth_token` (0600) | Bearer token shared between service and UI |

The Electron main process reads the token from disk and forwards it as a Bearer header (re-reading on 401/403 since the service regenerates it each start). The renderer never sees the token — all calls proxy through main. The API binds **loopback only** (NFR-S-01).

### Single-installer distribution ✅

A single installer bundles the Electron app **and** the Python service (compiled to a self-contained one-dir binary via PyInstaller, shipped under `resources/service`). No system Python required after install.

- **Windows:** NSIS `.exe` (per-machine, branded). Uninstall stops the service and removes the start-on-login launcher while preserving `~/.ambilight`.
- **macOS:** `.dmg` · **Linux:** `.AppImage` + `.deb` (configured; lightly tested).
- **Auto-update:** wired via `electron-updater` against **GitHub Releases** (each build emits `latest.yml`). Dormant until you publish a release from a real repo with `GH_TOKEN`.
- **Code signing / notarization:** env-driven config is in place (`WIN_CSC_LINK`/`CSC_KEY_PASSWORD`, Apple `APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID`). Until you supply certs, installers build **unsigned**.

### Building installers

```bash
# Python 3.12 + Node 20 + pnpm required. From the repo root:

# 1. Build the service binary (PyInstaller one-dir) → dist/service/ambilight-service
pip install pyinstaller
python build.py --service

# 2. Build the app + installer for the current OS
cd ui
pnpm install
pnpm run dist:win      # or dist:mac / dist:linux  (each runs gen:icons + vite build first)
# → installer in ui/release/  (e.g. "Ambilight Desktop Setup <version>.exe" + latest.yml)
```

`python build.py` (no flags) builds both the service and the UI for the host OS. CI mirrors this: `.github/workflows/build.yml` (PR/branch artifacts) and `.github/workflows/release.yml` (tag `v*` → signed build + publish to GitHub Releases).

> Design details: [Service Architecture doc](docs/06_service_architecture.md) · [Electron Architecture doc](docs/05_electron_architecture.md).


---

## 🚨 Known Limitations & Future Work

The service lifecycle, crash/display recovery, tray, start-on-login, multi-device, profiles, diagnostics, and packaged installers that earlier drafts of this README listed as "planned" are now **implemented and verified** (see [Feature Implementation Status](#-feature-implementation-status)). The genuine remaining gaps:

### Not yet implemented
- **Web dashboard** — intentionally skipped; Ambilight Desktop is a native app, not a web portal.
- **Hardware-DRM capture** — *cannot* be implemented: HDCP/PlayReady fullscreen video is OS-excluded from all capture APIs (WGC included). Not a roadmap item.

### Caveats
- **macOS / Linux**: installers are configured and the pipeline runs, but testing is light and capture is MSS-only (no GPU-accelerated or DRM capture).
- **Signing & auto-update**: config is in place but **inert** until you supply code-signing certs and a GitHub repo + `GH_TOKEN`. Unsigned Windows builds trigger SmartScreen; macOS auto-update needs signing + notarization.
- **Long-term NFRs** (CPU ≤ 5%, memory ≤ 150 MB, MTBF ≥ 7 days) are not yet profiled over extended runs.
- **Multi-device discovery**: give each managed device a real IP or MAC — an unreachable entry with no MAC can fall back to the first responsive controller on the subnet.

---

## Roadmap

**Delivered**
- ✅ Background service + REST/WebSocket API, loopback-only, token-secured
- ✅ Display-event + two-level crash recovery (Electron watchdog + in-service pipeline watchdog)
- ✅ Electron app: tray, minimise-to-tray, onboarding wizard, dashboard, diagnostics, logs, settings, devices, profiles
- ✅ Start-on-login (Windows Startup / macOS launchd / Linux systemd)
- ✅ Multi-device + multi-monitor, gradient engine, built-in profiles, import/export, effect scheduler + plugins
- ✅ Audio-reactive mode (system-audio loopback) + scene presets (sunrise / sunset / ocean / ambient)
- ✅ Functional WGC capture (default; captures hardware-overlay video DXGI misses)
- ✅ Visual zone-layout editor (per-edge counts + thickness, live preview, hot-reload)
- ✅ Auto profile switching by foreground application (FR-PROF-07)
- ✅ Packaged installers (PyInstaller + electron-builder), code-sign config, electron-updater, release CI
- ✅ Per-user (`~/.ambilight`) config/profile persistence

**Next**
- [ ] Activate signed builds + auto-update (supply certs + GitHub release feed)
- [ ] macOS / Linux hardening + long-term performance profiling

**Later**
- [ ] Custom effect SDK / community plugin marketplace
- [ ] Cloud profile sync · mobile companion app

---

## 📡 REST API Reference

All endpoints require an `Authorization: Bearer <token>` header **except** `GET /health`. The token is regenerated on each service start and written 0600 to `~/.ambilight/auth_token`. The API binds to `127.0.0.1` only (NFR-S-01).

### Health & status
- `GET /health` — unauthenticated liveness/readiness (used by the Electron supervisor).
- `GET /api/status` — service + pipeline status.
- `POST /api/service/restart` — restart the pipeline in-process.

```json
// GET /health
{ "status": "ok", "pipeline_alive": true, "paused": false, "restarts": 0,
  "fps": 29.3, "latency_ms": 34.2, "uptime_s": 3600.5 }
```

### Pipeline control
- `POST /api/pipeline/start` · `POST /api/pipeline/stop`
- `POST /api/pipeline/pause` · `POST /api/pipeline/resume`

### Configuration
- `GET /api/config` — full current configuration.
- `PUT /api/config` — delta update (unchanged fields preserved); persisted to the loaded config file and broadcast as a `CONFIG_UPDATE` hot-reload.

```
PUT /api/config
{ "color": { "mode": "kmeans" }, "capture": { "fps_target": 60 } }
```

### Profiles
- `GET /api/profiles` → `{ "profiles": ["gaming", "movie", "night"] }`
- `GET /api/profiles/{name}` — retrieve a profile.
- `POST /api/profiles/{name}` — save current config as a named profile.
- `DELETE /api/profiles/{name}` — delete a profile.
- `POST /api/profiles/{name}/apply` — load and apply a profile.
- `POST /api/profiles/{name}/import` — import a profile from a JSON body.

### Devices
- `GET /api/devices` — known/cached devices.
- `POST /api/devices/scan` — scan the subnet for controllers.
- `POST /api/devices/test` — flash a device: `{ "ip": "...", "port": 5577 }`.
- `GET /api/devices/{ip}/capabilities` — probe single-RGB vs addressable/zones.

### Effects & modes
```
PUT /api/mode
{ "mode": "screen_sync" | "static" | "breathing" | "rainbow" | "candle"
        | "sunrise" | "sunset" | "ocean" | "ambient" | "audio",
  "params": { "r": 255, "g": 100, "b": 50, "speed": 1.0 } }
```
- `audio` params: `{ "mode": "level" | "spectrum", "sensitivity": 1.0, "r","g","b" }`.
- `sunrise`/`sunset` params: `{ "duration": 300 }` (seconds).
- `GET /api/effects` — list selectable modes (built-ins + loaded plugins).

### Diagnostics, logs, foreground & auto-start
- `GET /api/diagnostics` — metrics history + system info.
- `GET /api/logs?level=INFO` — recent log lines (optional level filter).
- `GET /api/foreground` → `{ "app": "chrome.exe" }` — current foreground app (for auto-profile rules).
- `GET /api/autostart` · `POST /api/autostart/enable` · `POST /api/autostart/disable`.

> **Auto profile switching** (FR-PROF-07) is configured via the `auto_profile` block in `PUT /api/config` (or the Profiles tab): enable it, set per-app rules and an optional default profile, and the service applies the matching profile when the foreground app changes.

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
