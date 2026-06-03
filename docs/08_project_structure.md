# Updated Project Structure
## Ambilight Desktop — Production Repository Layout

**Version:** 1.0  
**Monorepo strategy:** Single repository, two independently deployable artifacts  
(Python service + Electron application)

---

## 1. Top-Level Repository

```
ambilight-desktop/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # PR validation: lint, typecheck, tests
│   │   ├── build.yml                 # Release: cross-platform packaging
│   │   └── nightly.yml               # Nightly smoke tests on all platforms
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docs/                             # Architecture and design documents
│   ├── 01_codebase_assessment.md
│   ├── 02_prd.md
│   ├── 03_trd.md
│   ├── 04_refactoring_plan.md
│   ├── 05_electron_architecture.md
│   ├── 06_service_architecture.md
│   ├── 07_migration_plan.md
│   └── 08_project_structure.md      ← this file
│
├── service/                          # Python service (the core product)
├── electron/                         # Electron desktop application
├── scripts/                          # Build, install, dev tooling
├── packaging/                        # Platform-specific packaging assets
│
├── .editorconfig
├── .gitignore
├── .gitattributes                    # LF line endings enforced
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

---

## 2. Python Service (`service/`)

```
service/
│
├── ambilight/                        # Core Python package
│   │
│   ├── __init__.py                   # Public API + version
│   │
│   ├── core/                         # Preserved + promoted existing modules
│   │   ├── __init__.py
│   │   ├── capture.py                # Screen capture (WGC/DXGI/MSS/PipeWire/SCK)
│   │   ├── color.py                  # 5 colour analysis modes
│   │   ├── config.py                 # YAML config → typed AppConfig dataclasses
│   │   ├── discovery.py              # Device discovery + MAC cache
│   │   ├── gpu.py                    # CuPy / OpenCV CUDA / CPU abstraction
│   │   ├── led_output.py             # MagicHome TCP protocol
│   │   ├── logging_setup.py          # Rotating logs + FPS metrics
│   │   ├── smoothing.py              # Adaptive EMA per-zone
│   │   └── zones.py                  # Frame-to-zone decomposition
│   │
│   ├── service/                      # New: service layer wrapping core
│   │   ├── __init__.py
│   │   ├── __main__.py               # Entry point: python -m ambilight.service
│   │   │
│   │   ├── api/                      # FastAPI application
│   │   │   ├── __init__.py
│   │   │   ├── app.py                # FastAPI app factory (create_app())
│   │   │   ├── auth.py               # Bearer token middleware
│   │   │   ├── websocket.py          # WS endpoint + broadcast manager
│   │   │   └── routers/
│   │   │       ├── __init__.py
│   │   │       ├── health.py         # GET /health, GET /service/status
│   │   │       ├── service.py        # POST /service/{start,stop,restart}
│   │   │       ├── config.py         # GET/PUT /config, GET /config/schema
│   │   │       ├── devices.py        # GET /devices, POST /devices/scan
│   │   │       ├── profiles.py       # CRUD /profiles
│   │   │       ├── effects.py        # GET/POST /effects
│   │   │       ├── diagnostics.py    # GET /diagnostics, GET /logs
│   │   │       └── schemas.py        # Pydantic models for all API types
│   │   │
│   │   ├── pipeline_controller.py    # Lifecycle mgmt: start/stop/pause/resume
│   │   ├── event_bus.py              # Internal async pub/sub (EventType enum)
│   │   │
│   │   ├── gradient_engine.py        # OKLab gradient generation for addressable LEDs
│   │   ├── effects_engine.py         # Effect registry + plugin loader
│   │   ├── profile_manager.py        # Profile CRUD + activation
│   │   ├── capability_probe.py       # MagicHome device capability detection
│   │   ├── diagnostics.py            # Metrics collection + persistence
│   │   ├── watchdog.py               # Internal process health monitoring
│   │   │
│   │   ├── platform/                 # OS-specific implementations
│   │   │   ├── __init__.py           # get_display_monitor() factory
│   │   │   ├── base.py               # DisplayMonitor + ServiceManager ABCs
│   │   │   ├── windows.py            # WM_DISPLAYCHANGE, NSSM service mgmt
│   │   │   ├── macos.py              # NSWorkspace, launchd service mgmt
│   │   │   └── linux.py              # udev, logind D-Bus, systemd service mgmt
│   │   │
│   │   └── effects/                  # Built-in effect implementations
│   │       ├── __init__.py
│   │       ├── base.py               # EffectPlugin ABC
│   │       ├── screen_sync.py        # Default: screen-matched colours
│   │       ├── static.py             # Static colour
│   │       ├── breathing.py          # Smooth pulse
│   │       ├── rainbow.py            # Hue cycle
│   │       ├── candle.py             # Warm flicker simulation
│   │       └── sunrise.py            # Warm-to-daylight ramp
│   │
│   └── cli/                          # CLI tools (dev + diagnostics)
│       ├── __init__.py
│       ├── main.py                   # python -m ambilight.cli (replaces root main.py)
│       └── scan.py                   # python -m ambilight.cli scan
│
├── tests/                            # Test suite
│   ├── __init__.py
│   ├── conftest.py                   # pytest fixtures (mock device, mock capture)
│   │
│   ├── unit/
│   │   ├── test_color.py             # All 5 analysis modes + edge cases
│   │   ├── test_smoothing.py         # EMA alpha behaviour, dead-zone
│   │   ├── test_zones.py             # Zone computation for various resolutions
│   │   ├── test_gradient.py          # OKLab interpolation accuracy
│   │   ├── test_config.py            # YAML load, merge, atomic write
│   │   ├── test_discovery.py         # Cache expiry, MAC matching
│   │   ├── test_led_output.py        # Command builder, duplicate suppression
│   │   └── test_event_bus.py         # Sync emit → async handler delivery
│   │
│   ├── integration/
│   │   ├── test_api_health.py        # /health endpoint with live service
│   │   ├── test_api_config.py        # PUT /config triggers hot-reload
│   │   ├── test_api_profiles.py      # Profile CRUD round-trip
│   │   ├── test_display_recovery.py  # Mock lock/unlock → pipeline restart
│   │   └── test_pipeline_e2e.py      # Full pipeline with mock capture + mock LED
│   │
│   └── fixtures/
│       ├── test_frame_1080p.npy      # Saved numpy array for reproducible tests
│       ├── test_frame_4k.npy
│       ├── config_minimal.yaml
│       └── config_full.yaml
│
├── packaging/
│   └── service/
│       ├── ambilight-service.spec    # PyInstaller spec (Windows/Linux)
│       ├── ambilight-service-mac.spec# PyInstaller spec (macOS)
│       ├── nssm.exe                  # Bundled NSSM for Windows service install
│       └── build.sh                  # CI: runs PyInstaller for current platform
│
├── configuration.yaml                # Default configuration (shipped in package)
├── requirements.txt                  # Core runtime dependencies
├── requirements-dev.txt              # Dev: pytest, mypy, ruff, watchdog
├── requirements-gpu.txt              # Optional: cupy, torch
├── pyproject.toml                    # Project metadata + tool config (ruff, mypy, pytest)
└── setup.py                          # Editable install for development
```

---

## 3. Electron Application (`electron/`)

```
electron/
│
├── src/
│   │
│   ├── main/                         # Main process (Node.js)
│   │   ├── index.ts                  # App entry: window, tray, service lifecycle
│   │   ├── service-controller.ts     # Python service start/stop/health-check
│   │   ├── ws-bridge.ts              # WebSocket relay: service → renderer IPC
│   │   ├── ipc-handlers.ts           # ipcMain.handle() registration
│   │   ├── tray.ts                   # Tray icon + context menu
│   │   ├── updater.ts                # electron-updater integration
│   │   ├── window.ts                 # BrowserWindow factory + state persistence
│   │   └── utils/
│   │       ├── paths.ts              # App/user data paths (platform-aware)
│   │       ├── token.ts              # Auth token reader
│   │       └── logger.ts             # electron-log setup
│   │
│   ├── preload/
│   │   ├── index.ts                  # contextBridge.exposeInMainWorld()
│   │   └── types.d.ts                # TypeScript types for window.ambilightAPI
│   │
│   └── renderer/                     # React application
│       │
│       ├── index.html                # Vite entry HTML
│       ├── main.tsx                  # React root mount
│       ├── App.tsx                   # Router + theme + event subscriptions
│       │
│       ├── theme/
│       │   ├── index.ts              # MUI theme definition
│       │   ├── colors.ts             # Brand colour tokens
│       │   └── typography.ts         # Font stack
│       │
│       ├── store/
│       │   ├── index.ts              # Zustand store root
│       │   ├── slices/
│       │   │   ├── service.ts        # serviceStatus, actions
│       │   │   ├── metrics.ts        # fps, latency, zoneColors
│       │   │   ├── config.ts         # config, configDirty, schema
│       │   │   ├── devices.ts        # devices[], scanning state
│       │   │   ├── profiles.ts       # profiles[], activeProfileId
│       │   │   ├── effects.ts        # activeEffect, availableEffects
│       │   │   └── logs.ts           # LogEntry[], level filter
│       │   └── selectors.ts          # Memoised derived state
│       │
│       ├── api/
│       │   ├── client.ts             # Typed fetch wrapper (calls window.ambilightAPI)
│       │   └── types.ts              # TypeScript interfaces for all API types
│       │
│       ├── components/
│       │   ├── AppShell/
│       │   │   ├── index.tsx         # Sidebar + top bar layout
│       │   │   ├── Sidebar.tsx       # Navigation links
│       │   │   ├── ServiceBar.tsx    # Start/stop/restart bar
│       │   │   └── StatusBadge.tsx   # Running/stopped/error indicator
│       │   │
│       │   ├── ZonePreview/
│       │   │   ├── index.tsx         # SVG screen outline with coloured zones
│       │   │   ├── ZoneRect.tsx      # Individual zone rectangle
│       │   │   └── useZoneColors.ts  # Zustand selector hook
│       │   │
│       │   ├── MetricsChart/
│       │   │   ├── FpsGauge.tsx      # Recharts radial gauge
│       │   │   ├── LatencyChart.tsx  # Line chart (60 s window)
│       │   │   └── useMetrics.ts
│       │   │
│       │   ├── DeviceCard/
│       │   │   ├── index.tsx
│       │   │   ├── ConnectionBadge.tsx
│       │   │   └── CapabilityBadge.tsx
│       │   │
│       │   ├── EffectPicker/
│       │   │   ├── index.tsx         # Effect grid with preview thumbnails
│       │   │   └── EffectCard.tsx
│       │   │
│       │   ├── LogViewer/
│       │   │   ├── index.tsx         # Virtualised log list (react-virtual)
│       │   │   ├── LogRow.tsx        # Coloured by level
│       │   │   └── LogFilter.tsx     # Level + search controls
│       │   │
│       │   └── common/
│       │       ├── ConfirmDialog.tsx
│       │       ├── LoadingSpinner.tsx
│       │       ├── PageSkeleton.tsx
│       │       ├── ColorSwatch.tsx
│       │       └── SectionHeader.tsx
│       │
│       └── pages/
│           ├── Dashboard/
│           │   ├── index.tsx         # Main landing page
│           │   ├── StatsRow.tsx      # FPS + latency summary cards
│           │   └── QuickActions.tsx  # Effect switcher + profile dropdown
│           │
│           ├── Devices/
│           │   ├── index.tsx
│           │   ├── DeviceList.tsx
│           │   ├── DeviceScanDialog.tsx
│           │   └── ManualAddDialog.tsx
│           │
│           ├── Effects/
│           │   ├── index.tsx
│           │   └── EffectConfig.tsx  # Per-effect config sliders
│           │
│           ├── Profiles/
│           │   ├── index.tsx
│           │   ├── ProfileList.tsx
│           │   ├── CreateProfileDialog.tsx
│           │   └── ImportExportButtons.tsx
│           │
│           ├── Settings/
│           │   ├── index.tsx         # Schema-driven form via @rjsf/mui
│           │   ├── CaptureSection.tsx# Manual override for capture settings
│           │   ├── ZoneEditor.tsx    # Visual zone layout editor
│           │   └── ResetDefaults.tsx
│           │
│           ├── Logs/
│           │   └── index.tsx
│           │
│           ├── Diagnostics/
│           │   ├── index.tsx
│           │   ├── HealthReport.tsx
│           │   └── CopyReportButton.tsx
│           │
│           └── Onboarding/
│               ├── index.tsx         # Wizard controller
│               ├── Step1Monitor.tsx
│               ├── Step2Device.tsx
│               ├── Step3Test.tsx
│               ├── Step4Profile.tsx
│               └── Step5AutoStart.tsx
│
├── build/                            # electron-builder assets
│   ├── icon.ico                      # Windows icon (256×256 + sizes)
│   ├── icon.icns                     # macOS icon
│   ├── icons/                        # Linux icon set (16, 32, 48, 64, 128, 256, 512 px)
│   │   └── *.png
│   ├── entitlements.mac.plist        # macOS sandbox entitlements
│   ├── nsis-installer.nsh            # Custom NSIS script (service install)
│   └── banner.bmp                    # NSIS installer banner (493×58)
│
├── package.json
├── tsconfig.json
├── tsconfig.node.json                # Main process TS config
├── vite.config.ts                    # Renderer build (Vite)
├── electron.vite.config.ts           # Main/preload build (electron-vite)
├── electron-builder.yml              # Packaging configuration
├── .eslintrc.cjs
└── .prettierrc
```

---

## 4. Scripts (`scripts/`)

```
scripts/
├── dev.sh                   # Start Python service + Electron in dev mode
├── dev.ps1                  # PowerShell equivalent for Windows
├── build-service.sh         # Run PyInstaller for current platform
├── install-service.sh       # Install systemd/launchd/NSSM service locally
├── uninstall-service.sh     # Remove service registration
├── sign-windows.ps1         # Code-sign with EV cert via signtool.exe
├── notarize-mac.sh          # Apple notarization via notarytool
├── test-install.sh          # Smoke test: install → start → /health → uninstall
└── generate-schema.py       # Dump AppConfig JSON Schema from Python → JSON file
```

---

## 5. User Data Directory (Runtime, not in repo)

```
~/.ambilight/                         # User data root (all platforms)
├── config.yaml                       # Active configuration (atomic writes)
├── auth_token                        # Service API auth token (mode 0600)
├── device_cache.json                 # Discovered device cache
│
├── profiles/
│   ├── builtin/
│   │   ├── gaming.json
│   │   ├── movie.json
│   │   ├── productivity.json
│   │   └── night.json
│   └── user/
│       └── <name>.json
│
├── plugins/                          # User-installed effect plugins
│   └── my_audio_effect.py
│
├── logs/
│   ├── ambilight.log
│   ├── ambilight.log.1
│   └── ambilight.log.2
│
└── metrics/
    └── latest.json                   # Rolling 60-second metrics window
```

---

## 6. pyproject.toml Configuration

```toml
[project]
name = "ambilight-desktop-service"
version = "1.0.0"
description = "Ambilight Desktop — Python service layer"
requires-python = ">=3.12"
dependencies = [
    "numpy>=1.26.0",
    "opencv-python>=4.9.0",
    "pyyaml>=6.0.1",
    "mss>=9.0.1",
    "Pillow>=10.0.0",
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.7.0",
    "watchdog>=4.0.0",
]

[project.optional-dependencies]
gpu = [
    "cupy-cuda12x>=13.0.0",
]
windows = [
    "dxcam>=0.0.5",
    "winsdk>=1.0.0b10",
    "comtypes>=1.4.1",
    "pywin32>=306",
]
macos = [
    "pyobjc-framework-Cocoa>=10.0",
    "pyobjc-framework-Quartz>=10.0",
]
linux = [
    "PyGObject>=3.46.0",
    "dbus-python>=1.3.2",
]
audio = [
    "sounddevice>=0.4.6",
    "numpy>=1.26.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "mypy>=1.10.0",
    "ruff>=0.4.0",
    "httpx>=0.27.0",      # For FastAPI TestClient
]

[project.scripts]
ambilight-service = "ambilight.service.__main__:main"
ambilight = "ambilight.cli.main:main"

[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "--cov=ambilight --cov-report=term-missing"

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "def __repr__", "if TYPE_CHECKING:"]
```

---

## 7. Key Interfaces (Contract Summary)

This table defines the boundaries between modules. These interfaces should never be violated without a corresponding update to consuming code.

| Producer | Interface | Consumer |
|---|---|---|
| `capture.py` | `CaptureBackend.grab() → ndarray \| None` | `pipeline_controller.py` |
| `color.py` | `ColorAnalyzer.analyze(region) → (R,G,B)` | `pipeline_controller.py` |
| `smoothing.py` | `SmoothingEngine.smooth_zones(list) → list` | `pipeline_controller.py` |
| `gradient_engine.py` | `GradientEngine.generate(zones, spec) → ndarray` | `led_output.py` |
| `led_output.py` | `MagicHomeController.set_rgb(r,g,b) → bool` | `pipeline_controller.py` |
| `event_bus.py` | `EventBus.emit(EventType, data)` | All service modules |
| `api/app.py` | `POST /config`, `GET /health`, `WebSocket /ws` | Electron main process |
| `preload/index.ts` | `window.ambilightAPI.*` | React renderer |
| `store/index.ts` | Zustand store actions + state | React pages + components |

---

## 8. Version Compatibility Matrix

| Component | Minimum | Recommended | Notes |
|---|---|---|---|
| Python | 3.12 | 3.12 | Bundled in installer |
| Node.js | 20 LTS | 22 LTS | Build-time only |
| Electron | 30 | 31 | Follow latest stable |
| React | 18.3 | 18.3 | |
| Windows | 10 22H2 | 11 23H2 | WGC requires ≥ 1903 |
| macOS | 13 Ventura | 14 Sonoma | ScreenCaptureKit requires ≥ 12.3 |
| Linux kernel | 5.15 | 6.6 | For DRM udev events |
| CUDA (optional) | 11.8 | 12.x | For CuPy GPU acceleration |
