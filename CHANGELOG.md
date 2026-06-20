# Changelog

All notable changes to **Ambilight Desktop** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
