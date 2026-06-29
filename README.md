<div align="center">

# 🌈 Ambilight Desktop

### Turn any screen into immersive ambient light — no proprietary hardware, no lock-in.

**Ambilight Desktop** mirrors what's on your display onto LED strips around it in real time, giving you the Philips Ambilight experience on the affordable MagicHome and WLED hardware you can already buy. It installs like a normal app, runs quietly in the background, and just works.

[![Build Status](https://github.com/LMC4910/ambilightRepo/actions/workflows/build.yml/badge.svg)](https://github.com/LMC4910/ambilightRepo/actions)
[![Version](https://img.shields.io/badge/version-2.1.0-6c5ce7.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Windows](https://img.shields.io/badge/Windows-Production%20Ready-success)](#platform-support)
[![macOS · Linux](https://img.shields.io/badge/macOS%20·%20Linux-Experimental-orange)](#platform-support)

<br/>

![Ambilight Desktop dashboard — live capture metrics, modes, and device status](Screenshot/Screenshot%202026-06-26%20134845.png)

<sub>The redesigned 2.0 desktop app — live FPS/latency, capture source, zone preview, and one-click modes.</sub>

</div>

---

## ⚡ What you get

- 🎥 **Real-time screen sync** — colours follow your display at ~30 FPS with **sub-50 ms** latency.
- 🎮 **Built for games & movies** — exclusive-fullscreen and hardware-overlay video light up correctly via Windows Graphics Capture (WGC).
- 🧩 **Works with the hardware you have** — **MagicHome / LEDENET** Wi-Fi controllers *and* **WLED** strips, behind one driver abstraction.
- 🖥️ **A real desktop app** — native Electron UI with system tray, first-run wizard, and a self-supervising background service that restarts itself if it ever crashes.
- 🏠 **Smart-home ready** — optional **MQTT bridge + Home Assistant** auto-discovery.
- 🔔 **Never miss a ping** — **Notification Flash** pulses your lights on OS notifications, even in fullscreen or while locked.
- 🐙 **Ambient GitHub awareness** — connect your GitHub account and flash on CI runs, pull requests, issues, releases and mentions, with your own colour rules (new in 2.1).
- 🆕 **Multi-PC aware** — several computers can share the same strips without fighting over them (new in 2.0).
- 🔒 **Local-first & private** — everything runs on your machine over your LAN. No cloud account, no telemetry.

---

## 🚀 Quick start

### Option A — Install the desktop app *(recommended)*

1. Download the installer for your OS from [**Releases**](https://github.com/LMC4910/ambilightRepo/releases) — on Windows that's `Ambilight Desktop Setup 2.1.0.exe`.
2. Run it and launch **Ambilight Desktop**.
3. The app starts its background service and walks you through a **5-step setup wizard**: pick a monitor → discover your controller → test it → choose a profile → optionally start on login.

Minimise the window to the tray and forget about it — your lights keep syncing whenever you're logged in.

> Prefer to build it yourself? See [Building installers](#building-installers).

### Option B — Run from source *(service / CLI)*

```bash
# Requires Python 3.12 (3.10+ works)
cd ambilightRepo
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# Find your controller, then put its IP in configuration.yaml
python main.py --discover

# Run the long-lived service (REST + WebSocket on 127.0.0.1:7826)
python -m ambilight.service

# …or the original one-shot CLI pipeline
python main.py
```

Run the Electron UI against a source checkout with `cd ui && pnpm install && pnpm run dev` — it spawns the service from your `.venv` automatically.

---

## ✨ Features in depth

### 🎥 Screen capture that actually works in games & video

A three-tier backend chain with automatic failover — **WGC → DXGI → MSS** — picks the best available source on every machine.

- **WGC (default)** captures the DWM-composited desktop, so **hardware-accelerated overlay video and exclusive-fullscreen games** that the older DXGI path renders black now light up correctly.
- **Self-healing & frame-verified:** a backend only counts as healthy once it returns a real frame; transient failures recover automatically instead of log-storming.
- **Multi-GPU correct:** DXGI binds to the GPU adapter that actually drives your chosen display.
- **Automatic HDR handling:** per-monitor HDR detection tone-maps washed-out HDR frames back to SDR before colour analysis.
- **Honest about DRM:** HDCP/PlayReady-protected fullscreen video (the Netflix app, some browser DRM) is excluded by Windows at the compositor and stays black under *every* capture API — that's the point of the DRM, not a bug. [More →](#video-appears-black)

### 🎨 Colour analysis & smoothing

- **5 analysis modes** — `average`, `edges`, `dominant`, `kmeans`, and the default `saturation_weighted` — plus a post-analysis **vibrance** control for punchy game colour.
- **Per-zone analysis** with a configurable **gradient engine** (linear / radial / ambient / screen-matched + gamma) for addressable strips.
- **Adaptive smoothing** — fast on scene cuts, gentle on subtle changes — eliminates flicker without lag.
- **Optional GPU acceleration** (CuPy / OpenCV CUDA / PyTorch) with automatic CPU fallback.

### 🧩 Devices & protocols

- **MagicHome / LEDENET** over TCP (port 5577) with MAC-based discovery that survives router restarts and IP changes.
- **WLED** strips stream **per-pixel over realtime UDP** with power via the JSON API; discovered via mDNS or an HTTP subnet probe.
- **Multi-device + multi-monitor:** one capture per monitor, shared across as many controllers as you like, each with its own LED count and zones.

### 🌅 Effects, scenes & automation

- **Modes:** `screen_sync`, `static`, `breathing`, `rainbow`, `candle`, plus the **sunrise / sunset / ocean / ambient** scene presets.
- **Audio-reactive** mode driven by system-audio loopback (level or spectrum).
- **Scheduler** for time-window effects (e.g. a sunrise alarm) and a **drop-in plugin loader** (`~/.ambilight/plugins`).
- **Profiles** — save / load / import / export, with built-in **Gaming**, **Movie**, and **Night** presets.
- **Auto profile switching:** map foreground apps to profiles and Ambilight swaps them live (game launches → Gaming profile).

### 🖥️ Multi-PC, smart home & alerts

- **🆕 Cross-instance device ownership.** Share one set of strips across several PCs without flicker: instances cooperatively claim devices, a deterministic rule elects a single owner, and a crashed owner's claim hands off automatically. Coordinates over your MQTT broker if you have one, otherwise a zero-config LAN announce. Transparent for single-PC setups.
- **🏠 MQTT bridge + Home Assistant.** Publishes live state, accepts commands, and auto-creates a Home Assistant device (light + profile selector + sensors). Off by default; broker credentials live in the OS keyring, never in plaintext.
- **🔔 Notification Flash.** Pulse the lights when an OS notification arrives — using the originating app's brand colour or a fixed one — with per-app overrides, keyword rules (incl. Phone Link forwarding), dedup, and a rate limit. Works in fullscreen, during Do Not Disturb, and while locked.
- **🐙 Ambient GitHub awareness.** A dedicated **Integrations** tab connects your GitHub account via the OAuth device flow and flashes the strip on CI runs, pull requests, issues, releases, mentions and security alerts. Colours come from your own rules, matched most-specific-first (workflow → repository → organisation → global). Polls by default; for repos you administer you can enable **instant webhook delivery** (a local cloudflared tunnel auto-registers hooks and those repos stop being polled). Off by default and a no-op until connected.

### 🛡️ Runs like real software

- **Self-supervising service:** the Electron app spawns, health-checks, and crash-restarts the bundled background service; it adopts an already-running one instead of double-spawning.
- **Survives the window closing** (minimise-to-tray) and can **start on login** (per-user, no admin).
- **Two-level crash recovery** (Electron watchdog + in-service pipeline watchdog, ≤10 s) and **display-event recovery** (pause/resume on sleep/wake/lock, rebuild on monitor changes).
- **Token-secured, loopback-only API** — the REST/WebSocket server binds to `127.0.0.1` and every call carries a per-session Bearer token.

---

## 🏗️ How it works

Ambilight Desktop ships as **two cooperating components** over one production pipeline core:

```
┌─────────────────────────────────────┐     ┌──────────────────────────────────────┐
│        Python background service    │     │        Electron desktop app          │
│                                     │     │                                      │
│  • Screen capture (WGC/DXGI/MSS)    │     │  • Spawns & supervises the service   │
│  • Colour analysis + smoothing      │◄────┤  • Tray + minimise-to-tray           │
│  • LED output (MagicHome / WLED)    │     │  • Wizard, dashboard, diagnostics    │
│  • REST API + WebSocket  :7826      │────►│  • Profiles / devices / settings     │
│  • Profile, config & ownership mgmt │     │  • Auto-update prompts               │
│                                     │     │                                      │
│  Runs in the user session          │     │  Minimise to tray — keeps running    │
└─────────────────────────────────────┘     └──────────────────────────────────────┘
         ▲                                            │
         │ start-on-login launcher (autostart.py)     │ spawn + health-check + restart
         │ Win Startup / launchd / systemd            │ (Electron watchdog)
         └────────────────────────────────────────────┘
```

**Why not a Windows Service?** Screen capture must run inside the *interactive user session* — a Session-0 SYSTEM service can't see the desktop/GPU output. So the desktop app supervises the service in your session instead, captures its logs to `~/.ambilight/logs/`, and restarts it if it dies. The capture pipeline itself runs in an isolated `multiprocessing` worker under its own watchdog.

| Channel | Endpoint | Purpose |
|---------|----------|---------|
| REST API (FastAPI) | `http://127.0.0.1:7826` | Config, profiles, devices, diagnostics, effects, autostart, ownership |
| WebSocket | `ws://127.0.0.1:7826/ws?token=…` | Real-time metrics (~10 Hz) |
| Auth token | `~/.ambilight/auth_token` (0600) | Per-session Bearer token shared service ↔ UI |

> Deep dives: [WLED setup](docs/wled.md) · [Home Assistant / MQTT](docs/home-assistant.md) · [Platform support](docs/platform__support.md).

---

## 🖱️ Platform support

| Platform | Status | Capture backends | Min version |
|----------|--------|------------------|-------------|
| **Windows 11** | ✅ **Production-ready** *(primary, fully verified)* | WGC · DXGI · MSS | 23H2 recommended |
| **Windows 10** | ✅ **Production-ready** | WGC · DXGI · MSS | 1903 (build 18362)+ |
| macOS | 🧪 Experimental | MSS only | 13 Ventura |
| Linux | 🧪 Experimental | MSS only | Ubuntu 22.04 LTS |

> **Windows is the supported, verified platform** — capture, the self-supervising service, installers, and recovery are all tested end-to-end. macOS and Linux builds run the core pipeline (MSS capture only, no GPU/overlay capture) and receive lighter testing; contributions to harden them are very welcome.

**Hardware you'll need:** a **MagicHome / LEDENET** Wi-Fi RGB controller (TCP 5577) **or** a **WLED** controller (realtime UDP + JSON API), on the same LAN as your PC. A CUDA-capable NVIDIA GPU is optional (it accelerates resize/analysis; CPU fallback is automatic).

---

## ⚙️ Configuration

Installed builds read and write `~/.ambilight/configuration.yaml` (seeded from a bundled default on first run); the repo `configuration.yaml` is the template. The config system uses **strict validation** and **atomic writes** (write-temp-then-rename) so a crash or power loss can't corrupt it, and **round-trips** any field it doesn't recognise.

Most people never touch it — the desktop app exposes everything — but the essentials are:

```yaml
device:
  ip: "192.168.1.29"          # your controller's IP
  mac: "aa:bb:cc:dd:ee:ff"    # optional, enables IP-change recovery
  protocol: magichome         # magichome | wled

capture:
  method: wgc                 # wgc | dxgi | mss
  monitor_index: 0            # 0 = primary
  fps_target: 30
  hdr: auto                   # auto | on | off

color:
  mode: saturation_weighted   # best quality / balance
```

Optional blocks: `devices:` (multi-controller), `zones:`, `smoothing:`, `gpu:`, `gradient:`, `effects:` (scheduler + plugins), `auto_profile:` (foreground-app rules), `mqtt:` (Home Assistant), `notifications:` (Notification Flash), and `ownership:` (multi-PC). The complete, documented schema is the `AppConfig` dataclass in [`ambilight/config.py`](ambilight/config.py).

| Env var | Effect |
|---|---|
| `AMBILIGHT_IP` / `AMBILIGHT_MAC` | Override device IP / MAC |
| `AMBILIGHT_MODE` | Override colour mode |
| `AMBILIGHT_FPS` | Override FPS target |
| `AMBILIGHT_MONITOR` | Override monitor index |
| `AMBILIGHT_GPU` | Override GPU backend (`cupy` / `opencv_cuda` / `torch` / `none`) |
| `AMBILIGHT_LOG_LEVEL` | Override log level |

---

## 📡 REST API

Every endpoint requires `Authorization: Bearer <token>` **except** `GET /health`. The token is regenerated on each service start and written `0600` to `~/.ambilight/auth_token`. The API binds to `127.0.0.1` only.

```http
GET  /health                      → liveness/readiness (unauthenticated)
GET  /api/status                  → service + pipeline status
POST /api/pipeline/{start|stop|pause|resume}
GET  /api/config                  → full configuration
PUT  /api/config                  → delta update + hot-reload (CONFIG_UPDATE)
GET  /api/profiles                → list profiles
POST /api/profiles/{name}         → save current config as a profile
POST /api/profiles/{name}/apply   → apply a profile
GET  /api/devices                 → known/cached devices
POST /api/devices/scan            → scan the subnet for controllers
POST /api/devices/test            → flash a device { "ip": "...", "port": 5577 }
PUT  /api/mode                    → set effect mode (screen_sync, audio, sunrise, …)
GET  /api/effects                 → selectable modes (built-ins + plugins)
GET  /api/diagnostics             → metrics history + system info
GET  /api/logs?level=INFO         → recent log lines
```

```json
// GET /health
{ "status": "ok", "pipeline_alive": true, "paused": false, "restarts": 0,
  "fps": 29.3, "latency_ms": 34.2, "uptime_s": 3600.5 }
```

```json
// ws://127.0.0.1:7826/ws?token=<token>  — streamed ~10 Hz
{ "fps": 29.3, "latency_ms": 34.2, "capture_time_ms": 12.5, "process_time_ms": 8.3,
  "led_transmit_ms": 2.1, "uptime_s": 3600.5, "cpu_usage": 4.2, "memory_usage_mb": 125.6 }
```

> The full set of endpoints and their request/response shapes lives in [`ambilight/api_server.py`](ambilight/api_server.py).

---

## 🚄 Performance

| Metric | Target | Measured |
|---|---|---|
| End-to-end latency | ≤ 50 ms | ~34–47 ms |
| Capture rate | ≥ 24 FPS | ~29 FPS (screen sync) |
| Crash recovery | ≤ 10 s | watchdog-verified |
| Config / profile persistence | survive restart | ✅ `~/.ambilight` |

**Tuning cheatsheet**

- **Lower CPU:** drop `fps_target` to 20, reduce analysis resolution (`analysis_width: 40`), or switch `kmeans` → `saturation_weighted`.
- **Smoother lights:** lower `smoothing.base_alpha` (e.g. `0.08`) and raise `min_change`.
- **Faster frames:** install `windows-capture` (WGC) + `dxcam` (DXGI), and CuPy for GPU resize (8–15 ms → 2–5 ms).

| Use case | `base_alpha` | `fast_alpha` | `fast_threshold` |
|---|---|---|---|
| Cinema / ambient | 0.08 | 0.40 | 80 |
| Gaming (default) | 0.15 | 0.55 | 60 |
| Reactive / party | 0.30 | 0.80 | 30 |

---

## 🛠️ Troubleshooting

<a id="video-appears-black"></a>

**Video appears black.** Make sure the **WGC** backend is active (`capture.method: wgc`, the default) — it fixes most "black video" cases by capturing the composited desktop. *Hardware-DRM fullscreen video (Netflix app, some browser DRM) is OS-excluded from every capture backend and stays black — there's no API to bypass it.* Use windowed/non-DRM playback if you need it lit.

**"No devices found."** Run `python main.py --discover` on the same network, confirm the controller is powered, check your `subnet` matches (e.g. `192.168.0.` vs `192.168.1.`), and ensure TCP 5577 isn't firewalled.

**"All backends exhausted."** Install MSS (`pip install mss`) as the guaranteed fallback — it's included in `requirements.txt`.

**Device IP changed after a router restart.** Set the `mac` field; discovery will re-find the controller by MAC. Run `python main.py --discover` to get it.

**Diagnose capture.** Run `python -m ambilight.service --selfcheck` to see which backends are available and producing real frames.

**Debug logging.** `python main.py --debug` or `AMBILIGHT_LOG_LEVEL=DEBUG python main.py` — logs per-frame RGB, zone results, and timing.

---

## 📦 Building installers

A single installer bundles the Electron app **and** the Python service (compiled to a self-contained binary via PyInstaller) — no system Python needed after install.

```bash
build-installer            # Windows  → ui\release\Ambilight Desktop Setup 2.1.0.exe (+ latest.yml)
./build-installer.sh       # macOS/Linux → ui/release/ (DMG, or AppImage + deb)
python build.py            # cross-platform equivalent the wrappers call
```

**Prerequisites:** Python 3.12 (`pip install -r requirements.txt`, which includes PyInstaller + the Windows capture backends), Node 20, and pnpm. Add `--service` / `--ui` to build one half, or `--gpu` for the large CuPy/CUDA build.

- **Windows:** NSIS `.exe` (per-machine, branded). Uninstall stops the service and removes the start-on-login launcher while preserving `~/.ambilight`.
- **macOS:** `.dmg` · **Linux:** `.AppImage` + `.deb`.
- **Auto-update:** wired via `electron-updater` against **GitHub Releases** (each build emits `latest.yml`).
- **Code signing / notarization:** env-driven config is in place (Windows `.pfx`, Apple Developer ID). Until you supply certificates, installers build **unsigned** — Windows shows a SmartScreen prompt and macOS auto-update stays inactive.

CI mirrors `python build.py`: [`build.yml`](.github/workflows/build.yml) builds PR/branch artifacts; [`release.yml`](.github/workflows/release.yml) builds and publishes to GitHub Releases on `v*` tags.

---

## 🗺️ Roadmap

**Shipped in 2.1**
- ✅ Integrations hub with Ambient GitHub awareness (OAuth device flow, user-defined colour rules)
- ✅ Instant webhook delivery for admin repos (cloudflared tunnel + auto-registered hooks)

**Shipped in 2.0**
- ✅ Ground-up desktop redesign (frameless shell, sidebar router, 5-step wizard, dedicated Zones page)
- ✅ Cross-instance device ownership (multi-PC, MQTT or LAN, automatic failover)
- ✅ Hardened, self-healing, frame-verified capture stack (multi-GPU correct, fully bundled backends)

**Next**
- [ ] Activate signed builds + auto-update (ship certs + a public release feed)
- [ ] macOS / Linux hardening (ScreenCaptureKit / PipeWire capture) + long-term performance profiling

**Later**
- [ ] Custom-effect SDK / community plugin marketplace
- [ ] Cloud profile sync · mobile companion app

A couple of honest notes for early adopters: long-term resource NFRs (CPU ≤ 5%, memory ≤ 150 MB, MTBF ≥ 7 days) aren't profiled over multi-day runs yet, and **hardware-DRM fullscreen capture is a permanent OS limitation, not a roadmap item.**

---

## 🤝 Contributing

Issues and PRs are welcome — especially macOS/Linux capture, new device protocols, and effect plugins. The test suite runs with `pytest` from the repo root; an opt-in live-hardware suite (`tests/test_live_hardware.py`) exercises real capture backends and GPUs. See [CHANGELOG.md](CHANGELOG.md) for what's new in each release.

## 📄 License

[MIT](LICENSE) — use it freely, contribute back.

<div align="center">
<sub>Built for people who think their monitor deserves a halo. ✨</sub>
</div>
