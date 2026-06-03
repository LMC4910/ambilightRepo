# Product Requirements Document (PRD)
## Ambilight Desktop — Ambient Lighting Platform

**Version:** 1.0  
**Status:** Draft for Engineering Review  
**Owner:** Product  

---

## 1. Product Vision

**Ambilight Desktop** is a cross-platform, production-grade ambient lighting platform that extends any display with dynamic, screen-reactive LED lighting. It delivers a premium Philips Ambilight experience on custom hardware — without proprietary lock-in.

The platform consists of a persistent background service and a native desktop control application, distributed as a single installer. Users configure it once and it works silently and reliably from that point forward.

**One-sentence positioning:**  
*The ambient lighting system that works the way it should — install, configure, forget.*

---

## 2. User Personas

### Persona A — The Home Theater Enthusiast ("Alex")
- Uses a 4K OLED TV with MagicHome LED strips behind it
- Watches Netflix, Disney+, and local media daily
- Technically capable but unwilling to maintain scripts
- Needs: DRM-bypass capture, movie-quality smoothing, zero manual restarts
- Values: reliability, colour accuracy, set-and-forget operation

### Persona B — The PC Gamer ("Jordan")
- Gaming PC with monitors and RGB LEDs on desk and behind panels
- Switches between gaming, streaming, and desktop frequently
- Runs GPU-intensive titles where any performance overhead is unacceptable
- Needs: low-latency reactive mode, game-aware profiles, fast colour response
- Values: zero FPS impact, instant colour reaction, per-game profiles

### Persona C — The Developer / Power User ("Sam")
- Interested in custom effects, automation, and integration
- Comfortable with APIs, JSON, and scripting
- Wants to write custom effects or integrate with Home Assistant
- Needs: REST API, webhook support, plugin/SDK interface
- Values: extensibility, documentation, programmatic control

### Persona D — The Casual User ("Riley")
- Set up LED strips following a YouTube tutorial
- Does not understand technical concepts
- Expects the application to work like a commercial product
- Needs: simple UI, auto-discovery, safe defaults, automatic updates
- Values: simplicity, reliability, visual feedback

---

## 3. Functional Requirements

### 3.1 Service Layer (FR-SVC)

| ID | Requirement | Priority |
|---|---|---|
| FR-SVC-01 | Service starts automatically on OS boot without user login | P0 |
| FR-SVC-02 | Service continues running when the UI application is closed | P0 |
| FR-SVC-03 | Service restarts automatically within 10 seconds after a crash | P0 |
| FR-SVC-04 | Service exposes a local WebSocket API on configurable port | P0 |
| FR-SVC-05 | Service exposes a local REST API for configuration management | P0 |
| FR-SVC-06 | Service supports hot-reload of configuration without restart | P1 |
| FR-SVC-07 | Service persists last-known-good state and restores on restart | P1 |
| FR-SVC-08 | Service exposes a `/health` endpoint returning structured status | P0 |
| FR-SVC-09 | Service logs to rotating files with configurable verbosity | P0 |
| FR-SVC-10 | Service supports graceful shutdown with LED off command | P0 |

### 3.2 Screen Capture (FR-CAP)

| ID | Requirement | Priority |
|---|---|---|
| FR-CAP-01 | Capture at 24–30 FPS with <5% CPU overhead on modern hardware | P0 |
| FR-CAP-02 | Automatically recover from monitor lock without restart | P0 |
| FR-CAP-03 | Automatically recover from monitor disconnect and reconnect | P0 |
| FR-CAP-04 | Automatically recover from sleep and wake events | P0 |
| FR-CAP-05 | Support DRM-protected content via WGC compositor capture | P1 |
| FR-CAP-06 | Support multi-monitor configurations | P1 |
| FR-CAP-07 | Support configurable per-monitor capture assignment | P2 |
| FR-CAP-08 | Detect and report capture resolution and frame rate to UI | P1 |
| FR-CAP-09 | Automatically select fastest available capture backend | P0 |
| FR-CAP-10 | Never introduce visible flickering in the captured application | P0 |

### 3.3 Colour Analysis (FR-CLR)

| ID | Requirement | Priority |
|---|---|---|
| FR-CLR-01 | Support five analysis modes: average, edges, dominant, kmeans, saturation_weighted | P0 |
| FR-CLR-02 | All modes configurable without restart | P1 |
| FR-CLR-03 | Ignore near-black and near-white pixels per configurable threshold | P0 |
| FR-CLR-04 | Weight saturated colours above neutral colours | P0 |
| FR-CLR-05 | Temporal smoothing with adaptive speed — slow for subtle changes, fast for cuts | P0 |
| FR-CLR-06 | Gamma-corrected colour interpolation for gradient output | P1 |
| FR-CLR-07 | Per-zone colour analysis with independent smoothing | P0 |

### 3.4 Device Management (FR-DEV)

| ID | Requirement | Priority |
|---|---|---|
| FR-DEV-01 | Auto-discover MagicHome devices on local network | P0 |
| FR-DEV-02 | Identify devices by MAC address, not IP | P0 |
| FR-DEV-03 | Detect IP changes after router restart and reconnect | P0 |
| FR-DEV-04 | Probe and report device capability (single RGB, zones, addressable) | P1 |
| FR-DEV-05 | Support multiple simultaneous devices | P2 |
| FR-DEV-06 | Display device health status (connected, latency, firmware version) | P1 |
| FR-DEV-07 | Allow manual device addition by IP/MAC from UI | P0 |
| FR-DEV-08 | Automatic reconnect with exponential back-off | P0 |

### 3.5 Gradient Engine (FR-GRAD)

| ID | Requirement | Priority |
|---|---|---|
| FR-GRAD-01 | Detect whether device supports per-LED addressable output | P1 |
| FR-GRAD-02 | Generate linear gradients across addressable LED strips | P1 |
| FR-GRAD-03 | Generate radial gradients centred on screen midpoint | P2 |
| FR-GRAD-04 | Generate ambient gradients that blend all four screen edges | P1 |
| FR-GRAD-05 | Emulate gradients in software for single-RGB devices via rapid switching | P2 |
| FR-GRAD-06 | Apply gamma correction to all gradient interpolation | P1 |
| FR-GRAD-07 | Support configurable LED count per strip segment | P1 |

### 3.6 Effects Engine (FR-EFF)

| ID | Requirement | Priority |
|---|---|---|
| FR-EFF-01 | Screen sync mode (current behaviour) | P0 |
| FR-EFF-02 | Static colour mode | P0 |
| FR-EFF-03 | Breathing effect (smooth pulse) | P1 |
| FR-EFF-04 | Rainbow cycle effect | P1 |
| FR-EFF-05 | Music/audio reactive mode (beat detection) | P2 |
| FR-EFF-06 | Scene presets (sunrise, sunset, candlelight, ocean) | P2 |
| FR-EFF-07 | Custom effect authoring via simple scripting API | P3 |
| FR-EFF-08 | Effect scheduling (night mode auto-dim at 22:00) | P2 |

### 3.7 Profile Management (FR-PROF)

| ID | Requirement | Priority |
|---|---|---|
| FR-PROF-01 | Save current settings as a named profile | P1 |
| FR-PROF-02 | Load profile from UI | P1 |
| FR-PROF-03 | Delete profile from UI | P1 |
| FR-PROF-04 | Export profile to JSON file | P2 |
| FR-PROF-05 | Import profile from JSON file | P2 |
| FR-PROF-06 | Built-in profiles: Gaming, Movie, Productivity, Night | P1 |
| FR-PROF-07 | Auto-switch profile based on foreground application | P3 |

### 3.8 Desktop UI (FR-UI)

| ID | Requirement | Priority |
|---|---|---|
| FR-UI-01 | Service start / stop / restart controls | P0 |
| FR-UI-02 | Real-time FPS and latency display | P1 |
| FR-UI-03 | Live colour preview showing current zone output | P1 |
| FR-UI-04 | Device list with connection status | P0 |
| FR-UI-05 | Effect selector with live preview | P1 |
| FR-UI-06 | Zone layout editor | P2 |
| FR-UI-07 | Log viewer with level filter | P1 |
| FR-UI-08 | Settings editor for all configuration fields | P0 |
| FR-UI-09 | System tray icon with quick controls | P1 |
| FR-UI-10 | Auto-minimise to tray on window close | P1 |
| FR-UI-11 | First-run onboarding wizard | P2 |
| FR-UI-12 | Diagnostic page with device test controls | P1 |

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement |
|---|---|
| NFR-P-01 | End-to-end latency (screen change → LED update) ≤ 50 ms at 30 FPS |
| NFR-P-02 | Service CPU usage ≤ 5% on a modern 4-core CPU during normal operation |
| NFR-P-03 | Service idle CPU usage ≤ 1% (display off, LED static) |
| NFR-P-04 | Service memory footprint ≤ 150 MB RSS including Python interpreter |
| NFR-P-05 | UI application startup ≤ 3 seconds on an SSD-equipped system |
| NFR-P-06 | Service startup ≤ 5 seconds from OS boot |
| NFR-P-07 | Zero visible impact on gaming frame rate (verified by FRAPS/CapFrameX) |

### 4.2 Reliability

| ID | Requirement |
|---|---|
| NFR-R-01 | Service MTBF ≥ 7 days continuous operation |
| NFR-R-02 | Crash recovery within 10 seconds via OS watchdog |
| NFR-R-03 | Display event recovery within 5 seconds of reconnect |
| NFR-R-04 | Device reconnect within 10 seconds of network restoration |
| NFR-R-05 | No data loss of configuration or profiles on crash |
| NFR-R-06 | Atomic configuration writes (no corruption on power loss) |

### 4.3 Compatibility

| ID | Requirement |
|---|---|
| NFR-C-01 | Windows 10 22H2 (build 19045) and Windows 11 |
| NFR-C-02 | macOS 13 Ventura and later |
| NFR-C-03 | Ubuntu 22.04 LTS, Fedora 38+, Arch Linux (rolling) |
| NFR-C-04 | Python 3.12 (bundled in installer, not system Python) |
| NFR-C-05 | MagicHome-compatible devices (flux_led protocol) |
| NFR-C-06 | 4K (3840×2160) display support without performance regression |

### 4.4 Security

| ID | Requirement |
|---|---|
| NFR-S-01 | Service API binds to 127.0.0.1 only — no network exposure |
| NFR-S-02 | API authentication token for UI ↔ service communication |
| NFR-S-03 | No telemetry without explicit user opt-in |
| NFR-S-04 | Config files stored in user-owned directories (not system-wide) |
| NFR-S-05 | Installer does not require admin for per-user mode |

### 4.5 Installability

| ID | Requirement |
|---|---|
| NFR-I-01 | Single-file installer (MSI/EXE on Windows, DMG on macOS, AppImage on Linux) |
| NFR-I-02 | Complete uninstall removes all files and services |
| NFR-I-03 | Auto-update mechanism with user notification |
| NFR-I-04 | Bundled Python runtime — no system Python dependency |
| NFR-I-05 | Installer completes without errors on clean OS installations |

---

## 5. User Stories

**Epic 1: First-time setup**

> As Riley, I want to install the application and have it discover my LED controller automatically, so that I don't need to know my device's IP address.

> As Riley, I want the application to ask me which monitor to capture from, so that I can set it up correctly without reading documentation.

**Epic 2: Daily operation**

> As Alex, I want the LEDs to continue working after my PC wakes from sleep, so I never have to manually restart the software.

> As Alex, I want smooth, cinema-quality colour transitions during movies, so that bright flashes don't produce jarring LED jumps.

**Epic 3: Gaming**

> As Jordan, I want a gaming profile that responds in under 50 ms to colour changes, so that the LEDs feel reactive during gameplay.

> As Jordan, I want to verify that the Ambilight software is not reducing my game's FPS, so I can use it without hesitation.

**Epic 4: Power users**

> As Sam, I want to call a REST API to change the current effect from my automation script, so I can integrate Ambilight with my smart home setup.

> As Sam, I want to write a custom audio-reactive effect in Python and load it as a plugin, so I don't have to wait for the official implementation.

---

## 6. Acceptance Criteria (Key Features)

### AC-01: Display Recovery
- **Given** the PC is locked and then unlocked  
- **When** the display becomes available  
- **Then** LED output resumes within 5 seconds without user intervention

### AC-02: Crash Recovery
- **Given** the Python service crashes unexpectedly  
- **When** the OS watchdog detects the process exit  
- **Then** the service is restarted within 10 seconds and LED output resumes

### AC-03: Device Reconnect
- **Given** the LED controller becomes unreachable (router restart)  
- **When** the device obtains a new IP address  
- **Then** the service discovers the new IP via MAC lookup within 30 seconds

### AC-04: No Flicker
- **Given** a GPU-intensive game is running at 120+ FPS  
- **When** Ambilight Desktop is running simultaneously  
- **Then** no visible flickering or frame stutter is introduced in the game

### AC-05: Service Independence
- **Given** the Electron UI application is closed  
- **When** the user observes the LEDs  
- **Then** LED output continues uninterrupted

---

## 7. Feature Prioritisation Matrix

```
Priority 0 (MVP — must ship)
  └── Service daemon with auto-start
  └── Display event recovery
  └── Electron UI with service controls
  └── Auto-discovery in UI
  └── Screen sync mode
  └── Stable, flicker-free capture
  └── Cross-platform installers

Priority 1 (v1.1 — ship within 60 days of MVP)
  └── Device capability detection
  └── Gradient engine for addressable strips
  └── Profile system (save/load)
  └── Built-in profiles (Gaming, Movie, Night)
  └── Real-time diagnostics in UI
  └── System tray with quick controls
  └── REST API for external control

Priority 2 (v1.2 — ship within 120 days)
  └── Multi-monitor support
  └── Audio reactive mode
  └── Zone layout editor
  └── Effect scheduler
  └── Profile import/export
  └── Web dashboard

Priority 3 (v2.0 — future)
  └── Plugin marketplace
  └── Custom effect SDK
  └── Mobile companion app
  └── Cloud profile sync
  └── Auto profile switching by application
```

---

## 8. Release Roadmap

| Milestone | Deliverable | Target | Exit Criteria |
|---|---|---|---|
| M0 — Foundation | Python service + REST/WS API | Week 4 | Service passes health check; API accepts config commands |
| M1 — Stability | Display event recovery + crash restart | Week 6 | AC-01, AC-02, AC-04 pass on clean Windows install |
| M2 — UI Alpha | Electron app basic controls | Week 10 | Start/stop/status visible; settings edit works |
| M3 — Beta | Profiles + gradients + tray | Week 14 | All P1 requirements met; no P0 regressions |
| M4 — Packaging | Platform installers + auto-update | Week 18 | Single-command install on Windows, macOS, Linux |
| M5 — Release | Public release + P2 features | Week 24 | All P0, P1 complete; P2 in progress |
