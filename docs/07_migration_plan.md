# Migration Plan
## Python Scripts → Unified Service → Electron Application → Production Release

**Version:** 1.0  
**Format:** Phase → Sprint → Task → Acceptance Criteria

---

## Migration Overview

```
CURRENT STATE                          TARGET STATE
──────────────                         ────────────
python main.py          ──────────►   Ambilight Desktop
  │                                     ├── Python Service (background)
  │  Manual execution                   │   ├── FastAPI REST + WebSocket
  │  Terminal required                  │   ├── Display event recovery
  │  No display recovery                │   ├── Gradient engine
  │  No UI                              │   ├── Effects engine
  │  Single device                      │   └── Profile manager
  │  No gradients                       │
  └──────────────────────               └── Electron Control Panel
                                              ├── Dashboard
                                              ├── Device management
                                              ├── Settings editor
                                              ├── Profile manager
                                              └── System tray

Timeline: 18 weeks, 1 engineer (12 weeks with 2 engineers)
```

---

## Phase 0 — Stabilisation (Weeks 1–2)
**Goal:** Fix the five critical issues in the existing scripts before adding anything new.  
**Risk:** Very Low — all changes are isolated and additive.

### Sprint 0.1: Critical Bug Fixes

#### Task 0.1.1 — Fix WGC capture border flag
```python
# ambilight/capture.py, WGCBackend.open()
session.IsBorderRequired = False   # ADD
session.IsCursorCaptureEnabled = False
```
- **AC:** No capture-induced flickering in a fullscreen game over 30-minute session
- **Effort:** 2 hours

#### Task 0.1.2 — Fix rate limiter drift
```python
# ambilight/capture.py, ScreenCaptureManager.grab()
# Replace time.sleep() with monotonic deadline approach
```
- **AC:** Capture rate stays within ±1 FPS of target over 5-minute run
- **Effort:** 2 hours

#### Task 0.1.3 — Atomic config writes
```python
# ambilight/config.py — write to tmp then os.replace()
```
- **AC:** Config survives a simulated crash during write (process kill during save)
- **Effort:** 4 hours

#### Task 0.1.4 — Device cache expiry
```python
# ambilight/discovery.py — reject entries older than 7 days
```
- **AC:** After 8 days, stale cache entries are ignored and a fresh scan occurs
- **Effort:** 2 hours

#### Task 0.1.5 — Remove WGC private API usage
```python
# ambilight/capture.py — use only dxcam public API
```
- **AC:** No calls to `dxcam._core.*`; unit test imports dxcam without error after version bump
- **Effort:** 4 hours

**Phase 0 deliverable:** `v0.1.0` — existing scripts, no new features, critical bugs resolved.  
**Total effort:** 1.75 points (~2 days)

---

## Phase 1 — Service Foundation (Weeks 2–6)
**Goal:** Transform the pipeline into a persistent service with a stable API.  
**Risk:** Medium — new async architecture alongside existing sync code.

### Sprint 1.1: Internal Event Bus (Week 2)

#### Task 1.1.1 — Implement EventBus
- Create `ambilight/service/event_bus.py`
- Define all `EventType` enum values
- Thread-safe `emit()` from sync threads + `emit_async()` from async context
- **AC:** Unit test: emit from thread, receive in async handler with <10 ms delay
- **Effort:** 1.5 points

#### Task 1.1.2 — Integrate EventBus into pipeline
- Pass bus instance to `AmbilightPipeline`
- Emit `DEVICE_CONNECTED`, `DEVICE_DISCONNECTED`, `PIPELINE_ERROR` events
- **AC:** Events logged to console when device disconnects and reconnects
- **Effort:** 0.5 points

### Sprint 1.2: Display Event Watcher (Week 3)

#### Task 1.2.1 — Windows display monitor
```python
# ambilight/service/platform/windows.py
# WM_DISPLAYCHANGE, WM_WTSSESSION_CHANGE, WM_POWERBROADCAST
```
- **AC (Windows):**
  - Lock PC → `SESSION_LOCKED` emitted within 1 s
  - Unlock PC → `SESSION_UNLOCKED` emitted within 1 s
  - Connect/disconnect external monitor → `DISPLAY_CHANGED` emitted
  - Sleep/wake cycle → `SLEEP` + `WAKE` emitted
- **Effort:** 2.5 points

#### Task 1.2.2 — macOS display monitor
```python
# ambilight/service/platform/macos.py
# NSWorkspace notifications + CGDisplay callback
```
- **AC (macOS):** Same scenarios as Windows
- **Effort:** 2 points

#### Task 1.2.3 — Linux display monitor
```python
# ambilight/service/platform/linux.py
# udev DRM events + logind D-Bus
```
- **AC (Linux):** Same scenarios; tested on X11 and Wayland
- **Effort:** 2.5 points

#### Task 1.2.4 — Platform factory
```python
# ambilight/service/platform/__init__.py
def get_display_monitor(bus: EventBus) -> DisplayMonitor: ...
```
- **AC:** Correct platform class returned on Windows, macOS, Linux
- **Effort:** 0.5 points

### Sprint 1.3: Pipeline Controller (Week 4)

#### Task 1.3.1 — Implement PipelineController
- Wraps `AmbilightPipeline` in a `multiprocessing.Process`
- Subscribes to display events from EventBus
- Implements `start()`, `stop()`, `pause()`, `resume()`
- **AC:**
  - Lock PC → pipeline pauses within 2 s; CPU drops to near-zero
  - Unlock PC → pipeline resumes within 5 s; LEDs update
  - `pause()` / `resume()` callable from API without UI
- **Effort:** 3 points

#### Task 1.3.2 — Survive display loss
- On `SESSION_LOCKED` / `SLEEP`: pause, turn off LEDs
- On `SESSION_UNLOCKED` / `WAKE`: wait 2 s, re-enumerate monitors, restart
- **AC:** Full lock/unlock cycle without manual restart; LEDs resume correctly
- **Effort:** 1 point

### Sprint 1.4: FastAPI Service (Weeks 4–5)

#### Task 1.4.1 — Service entry point
- Create `ambilight/service/__main__.py`
- Boot sequence: config → logging → auth token → bus → display monitor → controller → uvicorn
- **AC:** `python -m ambilight.service` runs without error; `/health` returns 200
- **Effort:** 2 points

#### Task 1.4.2 — REST API implementation
- `GET /health`, `GET /service/status`
- `POST /service/start`, `POST /service/stop`, `POST /service/restart`
- `GET /config`, `PUT /config`
- `GET /devices`, `POST /devices/scan`
- `GET /effects`, `POST /effects/activate`
- `GET /logs`, `GET /diagnostics`
- **AC:** All endpoints pass integration tests; `PUT /config` applies changes within 1 tick
- **Effort:** 3 points

#### Task 1.4.3 — WebSocket stream
- `/ws` endpoint with auth token validation
- Emit metrics at 2 Hz, log entries on generation, device events on change
- **AC:** wscat test client receives metrics within 600 ms of connection
- **Effort:** 1.5 points

### Sprint 1.5: Config Hot-Reload + Profiles (Week 5–6)

#### Task 1.5.1 — Config file watcher
- `watchdog`-based watcher on `config.yaml`
- On change: reload config, emit `CONFIG_CHANGED` event
- **AC:** Change YAML file manually → LEDs update within 2 s, no restart
- **Effort:** 1 point

#### Task 1.5.2 — Profile Manager
- CRUD on `~/.ambilight/profiles/`
- REST endpoints `/profiles/*`
- Built-in profiles: gaming, movie, productivity, night (bundled JSON)
- **AC:** `POST /profiles/:id/activate` switches effect and smoothing settings
- **Effort:** 2 points

**Phase 1 deliverable:** `v0.5.0` — Persistent service. API-controllable. Display-event-resilient.  
**Can be used without any UI via REST + curl.**  
**Total effort:** ~18 points (~4 weeks)

---

## Phase 2 — Capability and Effects (Weeks 6–10)

### Sprint 2.1: Device Capability (Week 6–7)

#### Task 2.1.1 — CapabilityProbe
- Send test commands, parse response to classify device
- Cache result in `device_cache.json`
- REST endpoint: `GET /devices/:id/capabilities`
- **AC:** Returns correct classification for single-RGB MagicHome controller
- **Effort:** 3 points

#### Task 2.1.2 — LED Device abstraction
- `LEDDevice` base class; `SingleRGBDevice` and `AddressableLEDDevice` subclasses
- `LEDOutputManager` routes to correct device type
- **AC:** Existing MagicHome controller works without behaviour change
- **Effort:** 2 points

### Sprint 2.2: Gradient Engine (Weeks 7–8)

#### Task 2.2.1 — OKLab interpolation
- Implement RGB → OKLab → RGB conversion (NumPy, no external deps)
- **AC:** Interpolation between red and blue produces perceptually uniform midpoints (verify visually)
- **Effort:** 1.5 points

#### Task 2.2.2 — Gradient modes
- `linear`, `radial`, `ambient`, `screen_matched`
- Gamma correction (γ=2.2)
- **AC:** 50-LED strip shows smooth gradient matching top/bottom zone colours
- **Effort:** 3 points

### Sprint 2.3: Effects Engine (Weeks 8–9)

#### Task 2.3.1 — EffectsEngine + registry
- Built-in: `screen_sync`, `static`, `breathing`, `rainbow`, `candle`
- Plugin loader from `~/.ambilight/plugins/`
- **AC:** Effect switch via API with <100 ms transition
- **Effort:** 3 points

#### Task 2.3.2 — Effect scheduling
- Cron-like schedule in config: `night_mode: {effect: static, color: [10,5,0], schedule: "22:00-07:00"}`
- **AC:** Night mode activates and deactivates at correct times
- **Effort:** 2 points

### Sprint 2.4: Diagnostics (Week 10)

#### Task 2.4.1 — Metrics persistence
- Rolling 60-second metrics window in `~/.ambilight/metrics/latest.json`
- **AC:** After reconnecting UI, last 60 s of FPS data renders in chart
- **Effort:** 1.5 points

**Phase 2 deliverable:** `v0.8.0` — Full-featured service. Gradients, effects, scheduling.  
**Total effort:** ~16 points (~5 weeks)**

---

## Phase 3 — Electron Application (Weeks 8–15)
*Begins at Week 8, overlaps with late Phase 2.*

### Sprint 3.1: Project Scaffold (Week 8)

#### Task 3.1.1 — Electron + React + Vite + TypeScript setup
```bash
npm create electron-vite@latest ambilight-desktop -- --template react-ts
```
- Configure paths, CSP, window settings
- **AC:** `npm run dev` opens Electron window with React app
- **Effort:** 1 point

#### Task 3.1.2 — Preload + contextBridge
- `ambilightAPI` surface: `service.*`, `api.*`, `on.*`
- TypeScript types for all API surfaces
- **AC:** Renderer can call `window.ambilightAPI.api.get('/health')` and receive response
- **Effort:** 1 point

### Sprint 3.2: Service Integration (Weeks 9–10)

#### Task 3.2.1 — ServiceController (main process)
- Start Python service on launch
- Health-check every 5 s; restart on failure
- Auth token management
- **AC:** Kill Python service manually → Electron detects and restarts within 10 s
- **Effort:** 2 points

#### Task 3.2.2 — WebSocket bridge
- Connect to service WS; forward messages to renderer via IPC
- Reconnect on disconnect
- **AC:** Renderer receives metrics updates within 600 ms of service start
- **Effort:** 1.5 points

### Sprint 3.3: Core UI (Weeks 10–13)

#### Task 3.3.1 — App shell + navigation
- Sidebar navigation: Dashboard, Devices, Effects, Profiles, Settings, Logs, Diagnostics
- Material UI theme (dark, with custom brand colours)
- Service control bar (start/stop/restart) always visible
- **AC:** Navigation works; service status badge updates in real-time
- **Effort:** 2 points

#### Task 3.3.2 — Dashboard
- Real-time FPS/latency gauges (recharts or Victory)
- Live zone colour display (SVG screen outline with coloured zones)
- Device status card
- Quick effect switcher
- **AC:** Dashboard updates at 2 Hz from WS stream; zone colours visually accurate
- **Effort:** 3 points

#### Task 3.3.3 — Device page
- Device list with status badges
- Scan button (triggers `POST /devices/scan`)
- Device test button (flash white 3×)
- Capability display
- Manual add by IP/MAC
- **AC:** Scanning finds test device; test button flashes LEDs; capability shown
- **Effort:** 2 points

#### Task 3.3.4 — Settings page
- Dynamic form rendered from JSON Schema (`GET /config/schema`)
- Grouped by section: Capture, Device, Zones, Color, Smoothing, GPU, Logging
- Validation before save
- Unsaved changes indicator
- **AC:** All config fields editable; invalid values prevented by schema; save applies within 2 s
- **Effort:** 3 points

#### Task 3.3.5 — Profiles page
- Profile list (built-in + user)
- Activate, delete, export, import
- Create from current settings
- **AC:** Profile switch applies within 1 s; export produces valid JSON; import succeeds
- **Effort:** 2 points

#### Task 3.3.6 — Logs page
- Real-time log viewer (WS stream)
- Level filter (DEBUG/INFO/WARNING/ERROR)
- Search
- Clear
- **AC:** WARNING+ messages appear within 1 s; filter shows only selected level
- **Effort:** 1.5 points

#### Task 3.3.7 — Diagnostics page
- FPS chart (last 60 s)
- Latency breakdown chart
- Device health timeline
- "Copy diagnostics report" button
- **AC:** Charts render historical data from `latest.json`; report is human-readable JSON
- **Effort:** 2 points

### Sprint 3.4: System Tray + Updater (Week 13)

#### Task 3.4.1 — System tray
- Tray icon + context menu: Open, Start/Stop, Profiles (submenu), Quit
- Icon badge: green (running), red (stopped/error), yellow (degraded)
- **AC:** Tray visible on all platforms; context menu works; icon reflects service state
- **Effort:** 1.5 points

#### Task 3.4.2 — Auto updater
- electron-updater + GitHub Releases
- Check on launch + 24 h
- User confirmation dialog
- **AC:** Staging release detected; dialog appears; update downloads and installs
- **Effort:** 1.5 points

### Sprint 3.5: Onboarding (Week 14–15)

#### Task 3.5.1 — First-run wizard
- Step 1: Monitor selection
- Step 2: Device scan + selection
- Step 3: Test LED strip (flash)
- Step 4: Choose profile
- Step 5: Enable auto-start
- Shown once; skippable; accessible from Help menu
- **AC:** New user can complete setup without documentation; LEDs flash on Step 3
- **Effort:** 2.5 points

**Phase 3 deliverable:** `v1.0.0-beta` — Full desktop application with service integration.  
**Total effort:** ~31 points (~7 weeks)**

---

## Phase 4 — Packaging (Weeks 15–18)

### Sprint 4.1: Python Service Bundle (Week 15–16)

#### Task 4.1.1 — PyInstaller spec files
```bash
# Windows
pyinstaller --onedir --name ambilight-service ambilight/service/__main__.py
# macOS  
pyinstaller --onedir --name ambilight-service ambilight/service/__main__.py
# Linux
pyinstaller --onefile --name ambilight-service ambilight/service/__main__.py
```
- Include: numpy, cv2, mss, yaml, fastapi, uvicorn
- Test: service bundle starts and responds to `/health`
- **AC:** Service binary starts independently of Python environment
- **Effort:** 3 points

#### Task 4.1.2 — Platform service installation scripts
- Windows: NSSM bundled in installer; `nssm install` on first run
- macOS: launchd plist written to `~/Library/LaunchAgents/` on first run
- Linux: systemd user unit written to `~/.config/systemd/user/` on first run
- **AC:** Service auto-starts after reboot on all three platforms
- **Effort:** 2 points

### Sprint 4.2: electron-builder (Week 16–17)

#### Task 4.2.1 — Build configuration
- `electron-builder.yml` as specified in Electron Architecture Document §7
- Windows: NSIS + MSI
- macOS: DMG (universal binary x64+arm64)
- Linux: AppImage + deb + rpm
- **AC:** `npm run dist` produces all packages; installers complete without errors on clean VMs
- **Effort:** 2.5 points

#### Task 4.2.2 — Code signing
- Windows: import code signing cert; configure `signingHashAlgorithms`
- macOS: configure `hardenedRuntime`, `entitlements`, `notarize`
- Linux: GPG-sign packages
- **AC:** No SmartScreen warning on Windows; Gatekeeper allows macOS install
- **Effort:** 1.5 points

### Sprint 4.3: CI/CD (Week 17–18)

#### Task 4.3.1 — GitHub Actions workflow
```yaml
# .github/workflows/build.yml
on: [push, pull_request]
jobs:
  test-python:
    runs-on: ubuntu-latest
    steps: [checkout, pip install, pytest]
  
  test-electron:
    runs-on: ubuntu-latest
    steps: [checkout, npm ci, npm run typecheck, npm run lint]
  
  build:
    if: startsWith(github.ref, 'refs/tags/v')
    strategy:
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
    steps: [checkout, pyinstaller, npm ci, npm run dist, upload-artifact]
  
  release:
    needs: build
    steps: [download-artifacts, create-github-release, upload-assets]
```
- **AC:** Green CI on all platforms; release tag produces all packages in GitHub Releases
- **Effort:** 2.5 points

**Phase 4 deliverable:** `v1.0.0` — Production-packaged, signed, auto-updating desktop application.  
**Total effort:** ~12 points (~3 weeks)**

---

## Rollback Strategy

Each phase produces a standalone deliverable with a version tag. If a phase introduces regressions:

| Phase | Rollback |
|---|---|
| Phase 0 | git revert; re-pin dependencies |
| Phase 1 | Revert to Phase 0 tag; `python main.py` still works |
| Phase 2 | Revert individual modules; service API remains stable |
| Phase 3 | Revert Electron changes; service still API-controllable via curl |
| Phase 4 | Re-build with previous tag; service binary independent |

---

## Dependency and Risk Map

```
Phase 0 ──► Phase 1.1 (EventBus) ──► Phase 1.2 (Display Events) ──► Phase 1.3 (PipelineCtrl)
                   │                                                          │
                   └──► Phase 1.4 (API Server) ──► Phase 1.5 (Profiles)      │
                                    │                                          │
                                    └──► Phase 2.1 (Capability) ──► Phase 2.2 (Gradients)
                                                                              │
Phase 1.4 ──► Phase 3.1 (Electron scaffold) ──► Phase 3.2 (Service integration)
                                                         │
                                               Phase 3.3 (Core UI) ──► Phase 3.4 (Tray + Updater)
                                                                                │
                                                                      Phase 4 (Packaging)
```

**Critical path:** Phase 0 → Phase 1 → Phase 3 → Phase 4  
**Parallel path:** Phase 2 can overlap with Phase 3 from Week 8 onward

---

## Total Effort Summary

| Phase | Points | Weeks | Cumulative |
|---|---|---|---|
| Phase 0 — Stabilisation | 2 | 2 | Week 2 |
| Phase 1 — Service Foundation | 18 | 4 | Week 6 |
| Phase 2 — Capability + Effects | 16 | 5 | Week 10 |
| Phase 3 — Electron Application | 31 | 7 | Week 15 |
| Phase 4 — Packaging | 12 | 3 | Week 18 |
| **Total** | **79** | **18** | |

With two engineers working in parallel on the service (weeks 2–8) and Electron (weeks 8–15), total calendar time is approximately **13 weeks** to `v1.0.0`.
