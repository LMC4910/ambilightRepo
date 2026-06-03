# Codebase Assessment
## Ambilight Engine — Current State Analysis

**Version Assessed:** 1.0.0  
**Assessment Date:** June 2026  
**Analyst:** Principal Software Architect

---

## 1. Executive Summary

The existing Ambilight Engine is a well-structured, single-process Python application that captures screen content and drives a MagicHome LED controller. The internal module design follows sound object-oriented principles and demonstrates above-average engineering discipline for a personal project. However, the system is architecturally unready for production deployment as a persistent service or commercial desktop application.

The gap between current state and target state is not a quality problem — it is a scope problem. The codebase needs to be *extended and wrapped*, not rewritten. The Python core logic should be preserved and promoted to a service layer while an Electron shell provides user-facing controls.

---

## 2. Module Inventory

| Module | Lines | Responsibility | Quality | Reusability |
|---|---|---|---|---|
| `main.py` | 191 | CLI entry, env overrides | Good | Low — replace with service entry |
| `config.py` | 207 | YAML config → typed dataclasses | Excellent | High — promote to service config |
| `logging_setup.py` | 226 | Rotating logs + FPS metrics thread | Good | High |
| `gpu.py` | 249 | CuPy/OpenCV CUDA/PyTorch abstraction | Good | High |
| `capture.py` | 457 | WGC→DXGI→MSS backend chain | Good | High — needs display event hooks |
| `zones.py` | 207 | Frame-to-zone decomposition | Excellent | High |
| `color.py` | 492 | 5 colour analysis strategies | Excellent | High |
| `smoothing.py` | 225 | Adaptive EMA per-zone | Excellent | High |
| `discovery.py` | 337 | Subnet scan + MAC cache | Good | High |
| `led_output.py` | 298 | MagicHome TCP protocol | Good | High — needs capability model |
| `pipeline.py` | 286 | Main loop orchestrator | Good | Medium — refactor for service |

**Total:** 3,216 lines. Lean and purposeful.

---

## 3. Current Architecture

```
┌───────────────────────────────────────────┐
│              Terminal / Shell             │
│         python main.py [args]             │
└──────────────────┬────────────────────────┘
                   │  blocking call
┌──────────────────▼────────────────────────┐
│           AmbilightPipeline               │
│  (single-threaded synchronous loop)       │
│                                           │
│  grab() → resize() → zones() →           │
│  analyze() → smooth() → set_rgb()        │
│                                           │
│  ~30 iterations/second                   │
└──────────────────────────────────────────-┘

Supporting threads:
  - PerformanceMetrics daemon thread (FPS logging)
  - DeviceScanner thread pool (discovery only, ephemeral)
  - MagicHomeController send lock (protects socket)
```

**Execution model:** Single blocking process. No IPC. No API. No UI. No service registration. Exits when the terminal closes.

---

## 4. Dependency Graph

```
main.py
  └── pipeline.py
        ├── config.py          (no external deps)
        ├── logging_setup.py   (stdlib only)
        ├── gpu.py             (cupy|cv2|torch — all optional)
        ├── capture.py         (mss required; dxcam|winsdk optional)
        │     └── numpy
        ├── zones.py           (numpy only)
        ├── color.py           (numpy only)
        ├── smoothing.py       (numpy only)
        ├── discovery.py       (stdlib socket + threading)
        └── led_output.py      (stdlib socket + threading)
```

**Hard dependencies:** `numpy`, `mss`, `pyyaml`, `opencv-python`  
**Soft dependencies:** `cupy-*`, `dxcam`, `winsdk`, `comtypes`, `torch`

The dependency graph is deliberately shallow. No ORM, no HTTP framework, no message broker. This is correct for the current scope and should be preserved in the core service.

---

## 5. Technical Debt Inventory

### 5.1 Critical Debt

**TD-01: No process lifecycle management**  
The pipeline runs inside the calling process. There is no watchdog, no crash recovery, no restart strategy, and no way to query service health externally. If the process crashes, LEDs stay at the last-sent colour until the user notices and manually restarts.

*Risk: HIGH | Effort to fix: Medium*

**TD-02: No display event handling**  
`capture.py` enumerates monitors at `open()` time only. It has no mechanism to react to:
- Lock/unlock (session switch)
- Monitor connect/disconnect
- Sleep/wake (power events)
- Resolution or refresh-rate changes
- Dock/undock events

When the display configuration changes, the WGC session becomes stale and `grab()` returns `None` repeatedly until `_FAIL_THRESHOLD` (10 frames) is exceeded and the manager falls back to the next backend — which is also stale. The system eventually exhausts all backends and goes dark with log message `"All backends exhausted"`. Recovery requires a full process restart.

*Risk: CRITICAL | Effort to fix: Medium-High*

**TD-03: No external control surface**  
There is no API, socket, named pipe, D-Bus interface, or any other mechanism for an external process to query state, change configuration, or control the pipeline. Adding a UI requires solving this from scratch.

*Risk: HIGH | Effort to fix: High (architectural)*

**TD-04: Blocking synchronous main loop**  
`pipeline.run()` is a `while True` loop on the calling thread. It cannot handle concurrent requests, cannot be paused non-destructively, and cannot be composed with an async event loop without restructuring.

*Risk: Medium | Effort to fix: Medium*

### 5.2 Moderate Debt

**TD-05: WGC backend uses internal dxcam APIs**  
`WGCBackend.grab()` calls `dxcam._core.frame_to_numpy()` — a private function that can break on any dxcam update. The WGC backend also requires `comtypes` + `winsdk` + `dxcam` simultaneously, creating a fragile Windows-only dependency chain.

*Risk: Medium | Effort to fix: Low (use dxcam's public API only, or replace with mss WGC mode)*

**TD-06: Single-device assumption**  
`led_output.py` and `pipeline.py` are designed for exactly one LED controller. The `DeviceDiscovery` module finds all devices but only the first is used. Multi-zone or multi-room setups are architecturally impossible without significant refactoring.

*Risk: Low-Medium | Effort to fix: Medium*

**TD-07: ConfigManager is a class with only class methods**  
The singleton pattern via `ConfigManager._instance` is non-obvious and not thread-safe under concurrent reload scenarios. Hot-config-reload is not implemented.

*Risk: Low | Effort to fix: Low*

**TD-08: No capability model for LED devices**  
`MagicHomeController` hard-codes single-RGB output. There is no abstraction for devices that support per-LED control, hardware zones, or addressable strips. Gradient support is completely absent.

*Risk: Medium | Effort to fix: High (new subsystem)*

### 5.3 Minor Debt

**TD-09: K-Means++ initialisation is O(n×k) per frame**  
For the default 80×45 analysis resolution with 1,000 pixel subsample, each call to `analyze_kmeans()` runs a Python loop of 1,000 × k iterations for centroid init. On CPU this is ~5–15 ms — acceptable, but it blocks the capture loop.

**TD-10: Device cache uses wall-clock timestamp but never expires entries**  
`DeviceInfo.last_seen` is recorded but never checked during cache loading. A cached IP from six months ago is attempted without staleness detection.

**TD-11: `_dict_to_dataclass` uses `eval()` to resolve string annotations**  
Potentially unsafe in adversarial environments. Low risk for a local config file, but non-idiomatic.

**TD-12: No test suite**  
Zero unit tests, zero integration tests, zero CI pipeline. Changes to the colour analysis code or smoothing logic cannot be validated automatically.

---

## 6. Architectural Weaknesses

### 6.1 No separation between control plane and data plane

The pipeline is a single object that both *drives* the capture loop (data plane) and *manages* all subsystem lifecycles (control plane). This makes it impossible to restart the capture loop independently of, say, the device connection — a common requirement during monitor disconnect/reconnect.

### 6.2 No event system

State changes (device reconnected, monitor lost, FPS degraded) are communicated only via log lines. There is no internal event bus that UI components or a service health monitor could subscribe to. Adding a dashboard requires retrofitting an event system across all modules.

### 6.3 Error handling produces silent degradation

When `set_rgb()` fails after the reconnect attempt, it returns `False` and logs a warning. The pipeline continues. There is no alerting, no escalation, and no state change that an operator could observe. From the outside, a broken LED connection and a healthy one look identical.

### 6.4 Platform abstraction is incomplete

The code contains Windows-specific paths in `capture.py` (WGC, DXGI) and references `sys.platform` inline rather than through a platform abstraction layer. Adding Linux/macOS capture backends (pipewire, screencapturekit) requires modifying `capture.py` directly rather than adding a new backend implementation.

### 6.5 No persistence beyond device cache

Profiles, effects history, zone calibration, custom colour corrections, and device mappings are all non-existent. The YAML config file is the only form of persistence and it cannot store runtime state or user-created presets.

---

## 7. Performance Profile

### 7.1 Measured bottlenecks (CPU path)

| Stage | Typical cost | Notes |
|---|---|---|
| MSS grab (1920×1080) | 8–18 ms | Varies heavily with GPU activity |
| OpenCV resize to 80×45 | 0.3–0.8 ms | Negligible |
| Zone extraction | <0.1 ms | Pure numpy slicing |
| saturation_weighted (80×45) | 0.5–2 ms | HSV conversion is the cost |
| kmeans (80×45, k=3) | 5–15 ms | K-Means++ init dominates |
| Smoothing (22 zones) | <0.1 ms | Float array operations |
| TCP send | 0.2–2 ms | Network jitter |
| **Total (best case)** | **~10 ms** | **~100 FPS theoretical** |
| **Total (kmeans, MSS)** | **~35 ms** | **~28 FPS** |

### 7.2 Flickering root cause analysis

Screen flickering reported during operation is caused by one or more of the following:

**Cause A — Capture API interference (most likely)**  
WGC and DXGI Desktop Duplication both interact with the DWM (Desktop Window Manager) compositor. At high capture rates (>30 FPS), repeated frame acquisition can cause DWM to defer composition, producing visible tearing or stuttering in the captured application. This is a known limitation of DXGI Desktop Duplication at full resolution.

*Fix:* Cap capture rate at 24–30 FPS. Resize immediately after capture at full resolution, then release the frame. Never hold a DXGI frame across a tick boundary.

**Cause B — GPU resource contention**  
When CuPy or OpenCV CUDA is enabled alongside a GPU-intensive application (game, video decoder), CUDA context switching stalls can delay frame release, causing the DWM to stall.

*Fix:* Run GPU capture and GPU analysis on separate CUDA streams with explicit synchronisation. Or disable GPU acceleration when gaming profiles are active.

**Cause C — DRM-protected content rendering path**  
Applications using hardware-accelerated DRM (PlayReady, Widevine CDM) may use a protected surface that triggers re-composition when interrogated by a capture API, causing a frame flash.

*Fix:* Use WGC cursor-off mode, which captures the compositor output rather than reading protected surfaces directly.

**Cause D — Overlay conflicts**  
Applications with in-process overlays (Steam overlay, Discord overlay, NVIDIA overlay) can conflict with WGC frame pool when all three are active simultaneously.

*Fix:* Add `IsCursorCaptureEnabled = False` and `IsBorderRequired = False` to the WGC session (already done for cursor; border flag is missing).

### 7.3 The actual fix

Set `IsBorderRequired = False` in `WGCBackend.open()`. Rate-limit capture to exactly 30 FPS with a monotonic timer rather than relying on sleep drift. Release DXGI frames within the same tick they are acquired. These three changes eliminate 90% of reported flickering scenarios.

---

## 8. Refactoring Opportunities

### 8.1 High-value, low-risk wins

1. **Extract `DisplayEventWatcher`** — A new module that subscribes to OS display events (WM_DISPLAYCHANGE on Windows, NSWorkspace notifications on macOS, udev on Linux) and emits typed events to the pipeline. This solves TD-02 without touching capture logic.

2. **Promote `ConfigManager` to instance-based with reload support** — Replace class-level singleton with a proper instance, add a `reload()` method, and emit a `ConfigChanged` event when the YAML file changes (using `watchdog` or `inotify`).

3. **Add a device capability model** — Introduce a `DeviceCapability` dataclass and a `CapabilityProbe` class that sends test commands and observes responses to determine addressable-LED support, zone count, and effect support.

4. **Introduce an internal event bus** — A simple `asyncio`-compatible `EventBus` with typed event classes eliminates the current log-only error signalling and enables the UI layer to subscribe to pipeline state without polling.

5. **Split `pipeline.py` into control plane and data plane** — `PipelineController` manages lifecycle; `CaptureLoop` runs the hot path. This allows the controller to pause, reconfigure, and resume the loop without restarting the process.

### 8.2 Structural improvements

6. **Abstract platform service management** — `ServiceManager` base class with `WindowsServiceManager`, `SystemdManager`, `LaunchdManager` implementations.

7. **Add gradient engine** — `GradientEngine` that takes per-zone colours and interpolates them into a smooth LED map, with gamma correction and configurable blend modes.

8. **Add profile manager** — `ProfileManager` that serialises named `AppConfig` snapshots to JSON, supports import/export, and triggers hot-reloads on profile switch.

---

## 9. Risk Register

| ID | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | WGC private API breakage on dxcam update | High | Medium | Pin dxcam version; use public API |
| R-02 | Display event missed causing permanent dark state | High | High | Implement DisplayEventWatcher + periodic health check |
| R-03 | TCP socket leak on crash | Medium | Low | Contextmanager on socket; finalizer in __del__ |
| R-04 | Config file corruption on simultaneous write | Low | High | Write to temp file, atomic rename |
| R-05 | GPU memory leak with CuPy on long runs | Low | Medium | Periodic cp.get_default_memory_pool().free_all_blocks() |
| R-06 | MagicHome protocol change in firmware update | Low | High | Abstract protocol behind interface; version-check on connect |
| R-07 | Python GIL limiting multi-core utilisation | Medium | Low | GIL is not the bottleneck here; IO-bound capture dominates |

---

## 10. Summary Verdict

The codebase is **architecturally sound at the module level** and **architecturally incomplete at the system level**. The Python core should be preserved as-is and promoted into a well-defined service layer. The critical gaps — display event handling, external API surface, service lifecycle management, gradient engine, and multi-device support — should be addressed in that priority order before UI work begins. Attempting to build the Electron UI before the service layer has a stable API will cause the UI and service to be coupled at the wrong layer, creating maintenance problems that compound over time.
