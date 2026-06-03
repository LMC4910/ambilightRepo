# Refactoring Plan
## Ambilight Engine → Ambilight Desktop Service

**Version:** 1.0  
**Effort Unit:** 1 point ≈ 1 developer-day (senior engineer)

---

## 1. Refactoring Philosophy

The existing Python codebase is treated as **preserved core logic**, not legacy code to be rewritten. The refactoring strategy is additive:

1. Wrap the existing pipeline in a service shell.
2. Add missing infrastructure (event bus, display monitor, API server).
3. Extend with new capability (gradients, effects, profiles).
4. Migrate the CLI entry point to a service entry point.
5. Build the Electron shell around the stable service API.

Modules are never deleted — they are either kept as-is, promoted, or extended. This minimises regression risk and preserves the tested colour analysis and smoothing logic.

---

## 2. Immediate Fixes (Week 1–2) — "Stop the Bleeding"

These are small, high-impact, low-risk changes that fix critical issues in the existing scripts before any architectural work begins.

### RF-01: Fix WGC Border Capture Flag
**File:** `ambilight/capture.py`, `WGCBackend.open()`  
**Problem:** `IsBorderRequired` flag not set; causes DWM interference at high capture rates.  
**Fix:**
```python
session.IsBorderRequired = False      # ADD THIS
session.IsCursorCaptureEnabled = False  # already present
```
**Effort:** 0.25 pts | **Risk:** None | **Impact:** Eliminates ~80% of flicker reports

---

### RF-02: Monotonic Rate Limiter in Capture Loop
**File:** `ambilight/capture.py`, `ScreenCaptureManager.grab()`  
**Problem:** `time.sleep(frame_interval - elapsed)` drifts when sleep overshoots.  
**Fix:**
```python
def grab(self) -> Optional[np.ndarray]:
    now = time.monotonic()
    deficit = self._frame_interval - (now - self._last_grab_time)
    if deficit > 0.0005:           # >0.5 ms headroom
        time.sleep(deficit)
    self._last_grab_time = time.monotonic()
    ...
```
**Effort:** 0.25 pts | **Risk:** None | **Impact:** Stable 30 FPS without drift accumulation

---

### RF-03: Atomic Config Writes
**File:** `ambilight/config.py`  
**Problem:** Direct YAML writes can corrupt the config file on crash.  
**Fix:**
```python
import tempfile, os, pathlib

def _save_config(cfg: AppConfig, path: Path) -> None:
    tmp = path.with_suffix('.yaml.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        yaml.dump(dataclasses.asdict(cfg), fh)
    os.replace(tmp, path)          # atomic on POSIX and Windows Vista+
```
**Effort:** 0.5 pts | **Risk:** None | **Impact:** Config survives power loss / crash

---

### RF-04: Device Cache Expiry
**File:** `ambilight/discovery.py`, `DeviceCache.load()`  
**Problem:** Stale cached IPs are attempted indefinitely.  
**Fix:** Reject cache entries older than 7 days:
```python
MAX_CACHE_AGE_SECONDS = 7 * 86_400

def load(self) -> list[DeviceInfo]:
    ...
    now = time.time()
    return [d for d in devices if now - d.last_seen < MAX_CACHE_AGE_SECONDS]
```
**Effort:** 0.25 pts | **Risk:** None | **Impact:** Prevents ghost device attempts

---

### RF-05: WGC Public API Only
**File:** `ambilight/capture.py`, `WGCBackend.grab()`  
**Problem:** Calls `dxcam._core.frame_to_numpy()` — private API.  
**Fix:** Replace with dxcam's public `get_latest_frame()` method, or fall through directly to the DXGI backend using dxcam's public interface only:
```python
# Use public API only
def grab(self) -> Optional[np.ndarray]:
    if self._camera is None:
        return None
    return self._camera.get_latest_frame()   # public method
```
**Effort:** 0.5 pts | **Risk:** Low | **Impact:** Removes brittle private API dependency

---

**Total immediate fixes: 1.75 points (~2 developer-days)**

---

## 3. Phase 1 — Service Foundation (Weeks 2–4) — 18 points

The goal of Phase 1 is a stable Python service with an HTTP/WebSocket API that the Electron app can talk to. No UI work yet.

### RF-06: Introduce Internal Event Bus
**New file:** `ambilight/service/event_bus.py`

```python
# Typed event system using asyncio queues
# All subsystems subscribe; PipelineController dispatches
```

**Effort:** 2 pts | **Depends on:** — | **Enables:** RF-07, RF-08, RF-09

---

### RF-07: Display Event Watcher
**New file:** `ambilight/service/platform/windows.py` (+ macos.py, linux.py)

Subscribes to OS-level display/session/power events and emits to event bus.

Windows: `WM_DISPLAYCHANGE`, `WM_WTSSESSION_CHANGE`, `WM_POWERBROADCAST`  
macOS: `NSWorkspaceScreensDidWakeNotification`, CGDisplay callback  
Linux: udev netlink socket for DRM events; logind D-Bus for sleep/wake

**Effort:** 5 pts | **Depends on:** RF-06 | **Enables:** RF-08

---

### RF-08: Refactor Pipeline into Controller + CaptureLoop
**New file:** `ambilight/service/pipeline_controller.py`  
**Modified:** `ambilight/pipeline.py` (becomes the CaptureLoop dataplane only)

`PipelineController` listens to event bus:
- `SESSION_LOCKED` → pause capture (save CPU)
- `SESSION_UNLOCKED` / `WAKE` → wait 2 s, re-enumerate monitors, restart capture
- `DISPLAY_CHANGED` → restart capture with new monitor config
- `SLEEP` → turn off LEDs, pause

**Effort:** 3 pts | **Depends on:** RF-06, RF-07 | **Enables:** RF-10

---

### RF-09: FastAPI Service Entry Point
**New file:** `ambilight/service/__main__.py`  
**New file:** `ambilight/service/api_server.py`

Starts uvicorn on 127.0.0.1:7826 (REST) and 127.0.0.1:7825 (WebSocket).  
Auth token generation and validation middleware.  
Implements all `/api/v1/*` endpoints from TRD §2.4.

**Effort:** 5 pts | **Depends on:** RF-06 | **Enables:** RF-11, RF-12

---

### RF-10: Config Hot-Reload
**Modified:** `ambilight/config.py`

Add `ConfigManager.reload()` and a file watcher using `watchdog`:
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigFileWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('config.yaml'):
            self._manager.reload()
            self._bus.emit(EventType.CONFIG_CHANGED)
```

**Effort:** 2 pts | **Depends on:** RF-03, RF-06 | **Enables:** UI config editing

---

### RF-11: Profile Manager
**New file:** `ambilight/service/profile_manager.py`

CRUD operations on `~/.ambilight/profiles/`.  
JSON serialisation of `AppConfig` snapshots.  
Bundled profiles: gaming, movie, productivity, night.  
REST endpoints `/profiles/*` wired to this class.

**Effort:** 3 pts | **Depends on:** RF-09 | **Risk:** Low

---

**Phase 1 total: ~18 points (~4 weeks, 1 engineer)**

---

## 4. Phase 2 — Capability Extension (Weeks 5–8) — 22 points

### RF-12: Device Capability Probe
**New file:** `ambilight/service/capability_probe.py`

Sends test commands and observes responses to classify:
- Single RGB (basic MagicHome)
- Zone-based (extended protocol)
- Addressable LED (SP108E / SK6812 controllers)

Caches capability in `device_cache.json`.

**Effort:** 4 pts | **Risk:** Medium (firmware diversity)

---

### RF-13: Gradient Engine
**New file:** `ambilight/service/gradient_engine.py`

OKLab-space interpolation between zone colours → per-LED array.  
Gamma correction (default γ=2.2).  
Output modes: linear, radial, ambient, screen_matched.  
Falls back to single-RGB combine when device is not addressable.

**Effort:** 5 pts | **Depends on:** RF-12

---

### RF-14: Effects Engine + Built-in Effects
**New file:** `ambilight/service/effects_engine.py`

Effect registry with hot-swap support.  
Built-in effects: screen_sync, static, breathing, rainbow, candle.  
Plugin loader from `~/.ambilight/plugins/`.

**Effort:** 5 pts | **Depends on:** RF-09

---

### RF-15: Multi-Device Support
**Modified:** `ambilight/service/pipeline_controller.py`  
**Modified:** `ambilight/led_output.py`

Replace single `MagicHomeController` with `DeviceManager` containing a list.  
Each device assigned to a zone group (e.g. device A = top+left, device B = bottom+right).  
Config schema extended with `devices: []` array.

**Effort:** 4 pts | **Risk:** Medium

---

### RF-16: Diagnostics + Metrics Persistence
**New file:** `ambilight/service/diagnostics.py`

Stores rolling 60-second window of FPS/latency in `~/.ambilight/metrics/latest.json`.  
Exposes `GET /diagnostics` and `GET /logs` endpoints.  
Triggered metric alerts on FPS degradation (<20 FPS for >5 s).

**Effort:** 3 pts

---

### RF-17: Audio Reactive Mode
**New file:** `ambilight/service/audio_capture.py`

Uses `sounddevice` (cross-platform WASAPI/CoreAudio/ALSA) to capture system audio.  
Beat detection via onset envelope analysis (librosa or custom NumPy).  
Colour pulse effect synchronized to detected beats.

**Effort:** 5 pts | **Risk:** Medium (platform audio APIs vary significantly)

---

**Phase 2 total: ~26 points (~6 weeks, 1 engineer)**

---

## 5. Phase 3 — Electron Application (Weeks 8–14) — 35 points

### RF-18: Electron Project Scaffold
**New directory:** `electron/`

```
electron/
  package.json
  vite.config.ts
  electron-builder.yml
  src/
    main/                   # Main process
    preload/                # Context bridge
    renderer/               # React app
```

**Effort:** 2 pts

---

### RF-19: Main Process — Service Lifecycle Controller
**New file:** `electron/src/main/service-controller.ts`

- Starts Python service on app launch
- Monitors health endpoint every 5 s
- Restarts service on crash
- Stops service on quit (respects "run in background" setting)
- Manages auth token

**Effort:** 4 pts

---

### RF-20: Main Process — WebSocket Bridge
**New file:** `electron/src/main/ws-bridge.ts`

Connects to `ws://127.0.0.1:7825`, receives service messages, forwards to renderer via IPC.

**Effort:** 2 pts

---

### RF-21: Renderer — Core React App
**Scope:**
- App shell with navigation
- Dashboard page (FPS, status, colour preview)
- Device page (list, scan, test)
- Settings page (all config fields, dynamic from JSON Schema)
- Profiles page (list, create, activate, export)
- Effects page (selector, preview)
- Diagnostics page (log viewer, metrics charts)
- Service control bar (start/stop/restart)

**Effort:** 14 pts | **Risk:** Medium (schema-driven settings form is the complex part)

---

### RF-22: System Tray Integration
**New file:** `electron/src/main/tray.ts`

Icon + context menu: Start/Stop/Restart, current status, open window.  
Badge on icon when device is disconnected.  
Windows jump list for quick profile switches.

**Effort:** 2 pts

---

### RF-23: Auto Updater
**New file:** `electron/src/main/updater.ts`

electron-updater integration with GitHub Releases.  
Check on launch + 24-hour interval.  
User notification dialog with changelog.  
Silent update option for enterprise.

**Effort:** 2 pts

---

### RF-24: First-Run Onboarding Wizard
**New file:** `electron/src/renderer/pages/Onboarding.tsx`

Step 1: Monitor selection  
Step 2: Device scan + selection  
Step 3: Test LED strip  
Step 4: Profile selection  
Step 5: Enable auto-start  

**Effort:** 3 pts

---

### RF-25: Zone Layout Visual Editor
**New file:** `electron/src/renderer/pages/ZoneEditor.tsx`

Drag-to-resize zone boundaries on a miniature screen representation.  
Numeric inputs for exact values.  
Live preview of zone split on captured frame.

**Effort:** 4 pts

---

**Phase 3 total: ~33 points (~7 weeks, 1 engineer)**

---

## 6. Phase 4 — Packaging and Distribution (Weeks 15–18) — 12 points

### RF-26: PyInstaller Service Bundle
Package Python service as self-contained binary for each platform.

Windows: `ambilight-service.exe` (PyInstaller one-dir)  
macOS: `ambilight-service` (PyInstaller one-dir, code-signed)  
Linux: `ambilight-service` (PyInstaller one-file, AppImage compatible)

**Effort:** 4 pts | **Risk:** High (PyInstaller quirks with NumPy/OpenCV)

---

### RF-27: electron-builder Configuration
Generate all platform packages:
- Windows: NSIS + MSI with NSSM service installation
- macOS: DMG with launchd plist installation
- Linux: AppImage + deb + rpm with systemd unit installation

**Effort:** 4 pts | **Risk:** Medium

---

### RF-28: Code Signing
- Windows: EV Code Signing Certificate via DigiCert / Sectigo
- macOS: Apple Developer certificate + notarization via `notarytool`
- Linux: GPG-signed packages + APT/RPM repository

**Effort:** 2 pts | **Note:** Requires purchased certificates

---

### RF-29: CI/CD Pipeline
GitHub Actions workflow:
- PR: lint + type-check + unit tests
- Main branch: build all platforms, run e2e tests
- Release tag: build, sign, upload to GitHub Releases

**Effort:** 3 pts

---

**Phase 4 total: ~13 points (~3 weeks, 1 engineer)**

---

## 7. Implementation Order and Dependencies

```
Week 1–2:  RF-01, RF-02, RF-03, RF-04, RF-05  (immediate fixes)
Week 2–3:  RF-06 (event bus)
Week 3–4:  RF-07 (display events)  ← requires RF-06
Week 3–4:  RF-09 (API server)      ← requires RF-06
Week 4:    RF-08 (pipeline ctrl)   ← requires RF-06, RF-07
Week 4:    RF-10 (config reload)   ← requires RF-06, RF-03
Week 4–5:  RF-11 (profiles)        ← requires RF-09
Week 5–7:  RF-12 (capability)
Week 6–8:  RF-13 (gradient)        ← requires RF-12
Week 6–8:  RF-14 (effects engine)  ← requires RF-09
Week 7–8:  RF-15 (multi-device)    ← requires RF-12
Week 7–8:  RF-16 (diagnostics)     ← requires RF-09
Week 8–9:  RF-18 (electron scaffold)
Week 9–10: RF-19 (service lifecycle)  ← requires RF-09
Week 9–10: RF-20 (WS bridge)          ← requires RF-19
Week 10–13:RF-21 (react app)          ← requires RF-20
Week 12:   RF-22 (tray)
Week 12:   RF-23 (updater)
Week 13:   RF-24 (onboarding)
Week 13–14:RF-25 (zone editor)
Week 15–16:RF-26 (PyInstaller)
Week 16–17:RF-27 (electron-builder)
Week 17–18:RF-28, RF-29 (signing, CI)
```

---

## 8. Risk Register for Refactoring

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| PyInstaller packaging breaks NumPy/OpenCV | High | High | Pin library versions; use `--collect-all` flags; test early |
| Display event API differs across Windows versions | Medium | High | Test on Win10 22H2 and Win11; graceful fallback to polling |
| NSSM service conflicts with antivirus | Medium | Medium | Sign the installer; whitelist documentation |
| FastAPI + uvicorn adds startup latency | Low | Low | Pre-warm at install time; lazy-load heavy routes |
| React settings form from JSON Schema is complex | Medium | Medium | Use `react-jsonschema-form` library; don't hand-code |
| macOS notarization delays releases | Medium | Low | Apply for cert early; automate notarization in CI |

---

## 9. Effort Summary

| Phase | Points | Calendar Weeks | Notes |
|---|---|---|---|
| Immediate Fixes | 2 | 2 | Can be done alongside Phase 1 |
| Phase 1 — Service Foundation | 18 | 4 | Unblocks all other work |
| Phase 2 — Capability Extension | 26 | 6 | Can overlap with Phase 3 from week 10 |
| Phase 3 — Electron Application | 33 | 7 | Starts week 8 |
| Phase 4 — Packaging | 13 | 3 | Starts week 15 |
| **Total** | **92** | **~18** | **1 senior engineer, no parallelism** |

With two engineers working in parallel (one on service, one on Electron), total calendar time reduces to approximately **12 weeks** to production packaging.
