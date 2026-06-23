# Changelog

All notable changes to **Ambilight Desktop** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-06-23

Feature release: a second LED protocol (WLED), automatic HDR handling and better
full-screen-game colour, a smart-home MQTT / Home Assistant bridge, and
Notification Flash. All additions are off by default or fully back-compatible;
existing MagicHome setups behave exactly as before.

### Added
- **WLED support.** A new `LedDriver` abstraction (`ambilight/devices/`) lets the
  pipeline drive multiple protocols; MagicHome is now one driver and **WLED** is
  the second. WLED streams per-pixel over realtime UDP (DRGB, chunked DNRGB for
  long strips) and uses the JSON API for power, with discovery via mDNS
  (`_wled._tcp`, when `zeroconf` is installed) or an HTTP subnet probe, plus
  manual IP entry. Each device gains a `protocol` field; the Devices page and
  onboarding are protocol-aware (selector, badges, protocol-aware test). See
  [docs/wled.md](docs/wled.md).
- **Automatic HDR detection + tone-mapping.** HDR displays are detected per
  monitor (Windows advanced-colour state); washed HDR frames are tone-mapped back
  to SDR before colour analysis. Mode is `auto` / `on` / `off` under
  `capture.hdr`.
- **Better full-screen-game colour.** A post-analysis **vibrance** control, and
  the built-in **Gaming** profile now uses the flagship `saturation_weighted`
  mode with vibrance and HDR-auto.
- **Capture-health surfacing.** The pipeline now detects a capture that delivers
  only black frames (a full-screen game on the MSS backend, or DRM-protected
  content) instead of reporting healthy while the strip is dark. The dashboard
  shows a clear banner ("Syncing • WGC", an MSS-fallback warning, or
  black / DRM / no-frames with the fix) and an HDR badge; `/health` and
  `/api/status` expose `capture_reason`, `capture_degraded`, and `hdr_active`.
- **MQTT bridge + Home Assistant discovery.** With a broker configured, Ambilight
  publishes live state and accepts commands over MQTT and auto-creates a Home
  Assistant device — a light (power / RGB / mode), a profile select, and
  FPS / syncing / devices sensors. Off by default; the broker password is stored
  in the OS keyring, never in `configuration.yaml`. Optional deps `paho-mqtt` +
  `keyring`. See [docs/home-assistant.md](docs/home-assistant.md).
- **Notification Flash.** Optionally flashes the LEDs when an OS notification
  arrives — using the originating app's icon colour or a fixed colour — so you
  notice alerts in full-screen, during Do Not Disturb / Focus Assist, or while
  the screen is locked. Per-app colour overrides and keyword rules (e.g. Phone
  Link / forwarded phone notifications), de-duplication, and a rate limit. New
  Notifications settings page with permission + test-flash.

### Changed
- **Force-quitting the desktop app no longer orphans the service.** The service
  watches the shell's PID and shuts itself down (turning the strip off) if the
  shell is force-killed (Task Manager / taskbar "End task") without running the
  graceful exit; graceful quit now tree-kills the bundled service so worker
  processes aren't left behind. (Closing the window still minimises to tray.)
- **Transient black frames are debounced** so brief dark scenes / scene cuts no
  longer blink the strip while still surfacing a sustained black-out.

### Security
- Broker credentials are stored in the OS keyring (Windows Credential Manager /
  macOS Keychain / Linux Secret Service) and scrubbed from the saved config; the
  MQTT/Home Assistant integration ships disabled by default.

[1.1.0]: https://github.com/LMC4910/ambilightRepo/releases/tag/v1.1.0

## [1.0.2] - 2026-06-21

Maintenance release fixing device discovery, service initialization crashes, and installer UX.

### Fixed
- **Device discovery completely rewritten.** Old code extracted MAC from wrong bytes (RGB color state instead of actual MAC), had no UDP broadcast support (primary discovery method), and hardcoded subnet to `192.168.1.0/24`. New implementation uses UDP broadcast to find devices in ~2s on any network, auto-detects local subnets, correctly parses real MAC from responses, and falls back to TCP only if UDP fails. Discovery now works reliably across different networks and finds devices 15x faster.
- **Service crashes on PyInstaller windowed builds.** `sys.stdout = None` in no-console builds caused `AttributeError: 'NoneType' object has no attribute 'isatty'` during module-level logging initialization in multiprocessing child processes. Added None checks before accessing `sys.stdout` methods and moved stream setup earlier in initialization pipeline.
- **Device cache write permission denied.** Cache path was relative (`device_cache.json`), which fails in read-only Program Files directory. Now resolved to `~/.ambilight/device_cache.json` before service starts.
- **LED count validation only warned.** Absurd values like 30000 now silently clamp to 30 instead of crashing the gradient engine.
- **Pipeline worker errors invisible.** Worker subprocess stderr was not captured, so early initialization errors disappeared silently. Now captured and logged.
- **Installation details pane hidden.** Added global `ShowInstDetails show` and `ShowUninstDetails show` directives to make NSIS installation logs visible by default. Installation now creates `~/.ambilight/logs/install.log` with version and metadata.

### Changed
- **Device discovery strategy.** Now tries: (1) direct IP verify, (2) UDP broadcast (primary), (3) cache lookup, (4) TCP scan fallback. Each step logs success/failure for diagnostics.

[1.0.2]: https://github.com/LMC4910/ambilightRepo/releases/tag/v1.0.2

## [1.0.1] - 2026-06-21

Bug-fix release focused on the three issues that broke real-world use — games not
lighting up, lights stuck static, and a stray terminal window — plus monitor-name
display, clean installs, and consistent versioning.

### Fixed
- **Fullscreen games / overlay video no longer capture black.** The fast capture
  backends were never installed, so despite `capture.method: wgc` the pipeline
  silently fell back to MSS (GDI/BitBlt), which renders exclusive-fullscreen
  games and hardware-accelerated overlay video black. WGC (`windows-capture`)
  and DXGI (`dxcam`) are now installed and bundled, and the service warns loudly
  if it ever has to fall back to MSS on Windows.
- **"Service active" but lights stay static.** `/health` previously reported
  `ok` purely on process liveness. It now reports `degraded` (with reasons) when
  the pipeline is running but not actually driving the LEDs — no device
  connected or capture producing no frames — while leaving intentional states
  (powered off, paused for sleep/lock) healthy. The pipeline also stops silently
  freezing the strip when capture returns no frames.
- **A terminal/console window popped up on launch.** The service is now built
  windowed (no console), the dev launcher spawns `pythonw.exe`, and a std-stream
  shim keeps logging/uvicorn working with no console attached.
- **Monitor names not shown on Setup, Devices and Diagnostics.** Names were
  fetched once on mount and failed while the service was still booting, leaving
  generic "Display N" placeholders; Diagnostics showed only resolutions. Monitor
  fetching now retries until the service answers, and real display names appear
  everywhere.
- **Broken/inconsistent configuration.** `configuration.yaml` had an
  out-of-range `monitor_index`, a string index, three conflicting MACs, and an
  absurd `led_count`. The file is normalized, values are validated/coerced at
  load time (with warnings), and an out-of-range `monitor_index` is clamped to a
  real display.

### Changed
- **Clean installs/updates.** The Windows installer now removes the previous
  version's files (including the bundled service's runtime `__pycache__` and
  files renamed between versions) before laying down the new version, so no stale
  files survive an update. User data in `%USERPROFILE%\.ambilight` is preserved.

### Added
- **Single source of truth for the app version.** Added `ambilight.__version__`
  (kept in lockstep with `ui/package.json`), exposed it on `/health` and
  `/api/status`, logged it at service boot, and added a `build.py` gate that
  fails the build if the Python and Electron versions drift.
- Tests for the new config validation and the degraded-health assessment.

[1.0.1]: https://github.com/LMC4910/ambilightRepo/releases/tag/v1.0.1
