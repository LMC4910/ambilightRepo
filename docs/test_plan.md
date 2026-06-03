# Ambilight Desktop — Test Plan

This document defines the exhaustive validation checklist for the Ambilight Desktop application.  
Every item **must pass** before a release binary is distributed.

---

## 1. Packaging Smoke Test (Clean VM)

> **Environment:** Fresh Windows 10/11 VM with **no Python, Node.js, or Visual Studio** installed.

| # | Test | Pass Criteria |
|---|------|---------------|
| 1.1 | Launch `AmbilightService.exe` from the `dist/service/` directory | Process starts, no crash within 10s |
| 1.2 | Verify `mss` import works | Service logs show `[Pipeline] Initialized` |
| 1.3 | Verify `dxcam` import works (if bundled) | Service logs show `[Capture] Using DXCam backend` |
| 1.4 | Verify `cupy` import works (if bundled) | Service logs show `[GPU] CuPy backend available` |
| 1.5 | Verify service listens on `127.0.0.1:7826` | `curl http://127.0.0.1:7826/api/status` returns JSON |
| 1.6 | Verify auth_token file is created | `~/.ambilight/auth_token` exists and is non-empty |
| 1.7 | Install the NSIS `.exe` installer | Installs without errors, creates Start Menu shortcut |
| 1.8 | Launch Electron UI from Start Menu shortcut | Window opens, shows Dashboard |

---

## 2. Service Recovery (Crash Resilience)

| # | Test | Pass Criteria |
|---|------|---------------|
| 2.1 | Kill `AmbilightService.exe` via Task Manager | Windows SCM restarts it within **5 seconds** |
| 2.2 | Kill service 3 times in rapid succession | Service restarts each time (5s/10s/30s delays) |
| 2.3 | Kill service while Electron UI is connected | UI shows `Service Offline`, then reconnects when service restarts |
| 2.4 | Stop service via `sc stop AmbilightService` | Service stops gracefully, no orphan processes |

---

## 3. Upgrade Simulation

| # | Test | Pass Criteria |
|---|------|---------------|
| 3.1 | Install v1.0.0, run service, then install v1.1.0 over it | Installer stops service, replaces binaries, starts service |
| 3.2 | After upgrade, verify `configuration.yaml` is preserved | User settings are not lost |
| 3.3 | After upgrade, verify `auth_token` is preserved | No re-auth required |
| 3.4 | After upgrade, verify `ambilight.log` is preserved | Log history is not wiped |
| 3.5 | Uninstall after upgrade | Service removed, Start Menu shortcut removed, no orphan files |

---

## 4. Multi-Monitor Resilience

> **Critical path**: `DXCam`, `MSS`, and Desktop Duplication behave differently across monitor topologies.

| # | Test | Pass Criteria |
|---|------|---------------|
| 4.1 | Single monitor (primary) | Capture works, LED output correct |
| 4.2 | Dual monitor — capture primary | Only primary monitor captured |
| 4.3 | Dual monitor — capture secondary (via `monitor_index: 1`) | Secondary monitor captured correctly |
| 4.4 | Triple monitor setup | All 3 monitors addressable via config |
| 4.5 | Hot-plug: Disconnect monitor while running | Service recovers gracefully, no crash |
| 4.6 | Hot-plug: Connect new monitor while running | Service detects new monitor (on next restart or config reload) |
| 4.7 | Change primary monitor in Windows Settings | Service continues to capture the correct monitor after restart |

---

## 5. OS Lifecycle Events

| # | Test | Pass Criteria |
|---|------|---------------|
| 5.1 | Sleep → Wake | Service resumes capture within 5 seconds |
| 5.2 | Hibernate → Resume | Service resumes capture within 10 seconds |
| 5.3 | Lock screen → Unlock | Service resumes capture immediately |
| 5.4 | Fast User Switching | Service continues running in original session |
| 5.5 | System reboot | Service starts automatically (delayed-auto) |

---

## 6. Auth & Security

| # | Test | Pass Criteria |
|---|------|---------------|
| 6.1 | API request without Bearer token | Returns 401 |
| 6.2 | API request with wrong token | Returns 401 |
| 6.3 | WebSocket connection without token | Connection rejected (1008) |
| 6.4 | Token file is readable only by current user | File permissions are restrictive |
| 6.5 | Service restart regenerates token | Old token stops working, Electron reads new token |

---

## 7. Electron UI Functional Tests

| # | Test | Pass Criteria |
|---|------|---------------|
| 7.1 | Dashboard shows real-time FPS | Value updates every ~100ms |
| 7.2 | Switch mode to `rainbow` | Service switches, LEDs display rainbow |
| 7.3 | Switch mode to `screen_sync` | Service switches back, LEDs match screen |
| 7.4 | Diagnostics tab shows log content | Log lines visible with green monospace font |
| 7.5 | "Open Log Folder" button | Opens `~/.ambilight/logs/` in Explorer |
| 7.6 | "Clear Logs" button | Log viewer clears, file is emptied |
| 7.7 | Service goes offline → Dashboard shows "Service Offline" | Status badge turns red |
| 7.8 | Service comes back online → Dashboard auto-reconnects | Status badge turns green, metrics resume |

---

## 8. Performance Baseline

| # | Metric | Target |
|---|--------|--------|
| 8.1 | Capture FPS (1080p, no GPU) | ≥ 30 FPS |
| 8.2 | Capture FPS (1080p, DXCam) | ≥ 60 FPS |
| 8.3 | End-to-end latency (capture → LED output) | ≤ 50ms |
| 8.4 | Service idle CPU usage (paused/no capture) | ≤ 1% |
| 8.5 | Service active CPU usage (1080p capture) | ≤ 15% |
| 8.6 | Service memory usage (steady state) | ≤ 200 MB |
| 8.7 | WebSocket metrics rate to UI | ~10 Hz |
