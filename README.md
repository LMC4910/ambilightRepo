# Ambilight Engine

Production-grade, GPU-accelerated Ambilight system for MagicHome LED controllers.  
Inspired by Philips Ambilight — built to rival it.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py  (CLI entry)                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   AmbilightPipeline   │  pipeline.py
                    │  (orchestrates all)   │
                    └──┬────┬────┬────┬────┘
                       │    │    │    │
         ┌─────────────┘    │    │    └──────────────────┐
         │                  │    │                        │
┌────────▼───────┐  ┌───────▼──────┐  ┌──────────────────▼──────┐
│ ScreenCapture  │  │  ZoneManager │  │    ColorAnalyzer         │
│  Manager       │  │  zones.py    │  │    color.py              │
│  capture.py    │  └──────────────┘  │                          │
│                │                    │  • average               │
│  WGC  ──────┐  │  ┌──────────────┐  │  • edges                 │
│  DXGI ──────┤  │  │GpuAccelerator│  │  • dominant              │
│  MSS  ──────┘  │  │  gpu.py      │  │  • kmeans                │
└────────────────┘  └──────────────┘  │  • saturation_weighted   │
                                       └──────────────────────────┘
         ┌──────────────────────────────────┐
         │         SmoothingEngine          │
         │         smoothing.py             │
         │  Adaptive EMA per zone + combined│
         └──────────────────┬───────────────┘
                            │
         ┌──────────────────▼───────────────┐
         │      MagicHomeController         │
         │      led_output.py               │
         │  Thread-safe TCP, reconnect,     │
         │  duplicate suppression, rate     │
         │  limiting                        │
         └──────────────────────────────────┘

Support modules
───────────────
  config.py        YAML config → typed AppConfig dataclass
  discovery.py     Subnet scanner + MAC-based cache
  logging_setup.py Rotating logs + FPS/latency metrics
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Load/validate YAML config, expose typed `AppConfig` |
| `logging_setup.py` | Rotating file + coloured console logging, background FPS metrics |
| `gpu.py` | Detect CuPy / OpenCV CUDA / PyTorch; CPU fallback; unified API |
| `capture.py` | WGC → DXGI → MSS backend chain with auto-failover |
| `zones.py` | Slice analysis frame into edge zones |
| `color.py` | 5 colour-analysis modes; zone combiner |
| `smoothing.py` | Adaptive EMA per zone + single combined output |
| `discovery.py` | Parallel TCP scan; MAC-based caching; reconnect |
| `led_output.py` | MagicHome TCP protocol; rate limit; reconnect |
| `pipeline.py` | Orchestrates all modules in the main loop |
| `main.py` | CLI argument parsing, environment overrides, entry point |

---

## Setup

### 1. Requirements

- **Python 3.12** (3.10+ also works)
- Windows 10/11 (for WGC/DXGI backends; MSS works on macOS/Linux)
- A MagicHome-compatible LED controller on the same network

### 2. Install

```bash
# Clone / download the project
cd ambilight

# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# Install core dependencies
pip install -r requirements.txt

# Optional: fast Windows capture (DXGI backend)
pip install dxcam

# Optional: Windows Graphics Capture API
pip install winsdk comtypes pywin32

# Optional: GPU acceleration (pick your CUDA version)
pip install cupy-cuda12x        # CUDA 12.x
# pip install cupy-cuda11x      # CUDA 11.x
```

### 3. Configure

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

### 4. Discover your device

```bash
python main.py --discover
```

Prints all MagicHome controllers found on your subnet with their IPs and MACs.

### 5. List monitors

```bash
python main.py --list-monitors
```

### 6. Run

```bash
python main.py
python main.py --config /path/to/custom.yaml
python main.py --ip 192.168.1.50 --mode kmeans --debug
```

---

## Performance Optimisation

### Capture backend selection

| Backend | Latency | DRM bypass | Platform |
|---|---|---|---|
| WGC | ★★★ | Yes (compositor) | Windows 10 1903+ |
| DXGI (dxcam) | ★★★ | No | Windows |
| MSS | ★★ | No | All |

Install `dxcam` and `winsdk` to unlock the two fastest backends.

### Analysis resolution

The default 80×45 pixels (= 3,600 pixels) gives excellent quality with
negligible CPU load.  Reduce to 40×22 for embedded/low-power systems;
increase to 160×90 for higher accuracy with the `kmeans` mode.

### GPU acceleration

With CuPy installed and a CUDA GPU available:

- Frame resize happens entirely on the GPU.
- Weighted mean calculations are parallelised across thousands of pixels.
- End-to-end latency typically drops from 8–15 ms to 2–5 ms.

If no GPU is detected the system silently falls back to NumPy on CPU.

### Smoothing tuning

| Use case | `base_alpha` | `fast_alpha` | `fast_threshold` |
|---|---|---|---|
| Cinema / ambient | 0.08 | 0.40 | 80 |
| Gaming (default) | 0.15 | 0.55 | 60 |
| Reactive / party  | 0.30 | 0.80 | 30 |

### Network overhead

- `min_change: 2` suppresses transmissions for imperceptible colour changes
  (saves ~30% of packets on static scenes).
- `TCP_NODELAY` is set on the socket to eliminate Nagle's algorithm delay.
- Duplicate-colour suppression prevents re-sending the same RGB value.

---

## Troubleshooting

### "No MagicHome devices found"

1. Run `python main.py --discover` from the same network.
2. Verify the controller is powered and connected (blue LED on most units).
3. Check `subnet` in config matches your network (e.g. `192.168.0.` not `192.168.1.`).
4. Firewall: ensure TCP port 5577 is not blocked.

### "All backends exhausted — no capture source available"

- **Windows**: install `mss` (`pip install mss`) as the guaranteed fallback.
- **Linux/macOS**: only MSS is supported; make sure it is installed.

### DRM-protected content appears black

- Use the **WGC backend** (`method: wgc`) — it captures the GPU compositor
  surface which includes decoded video on most streaming apps.
- Install `winsdk` and `comtypes`: `pip install winsdk comtypes pywin32`.
- Some apps (e.g. Netflix UWP) block even WGC; use browser-based streaming
  instead.

### High CPU usage

1. Lower `fps_target` (e.g. 20).
2. Reduce analysis resolution (`analysis_width: 40`, `analysis_height: 22`).
3. Switch from `kmeans` to `saturation_weighted` or `average`.
4. Install GPU acceleration (CuPy or PyTorch CUDA).

### LED flickering / colour jumping

1. Lower `base_alpha` (e.g. 0.08) for slower, smoother transitions.
2. Raise `min_change` (e.g. 5) to suppress minor variations.
3. Lower `adaptive_fast_threshold` (e.g. 40) to react more gradually to
   medium-sized changes.

### Device IP changed after router restart

- Set the `mac` field in config to your controller's MAC address.
  The discovery module will scan the subnet to find the new IP automatically.
  Use `python main.py --discover` to find the MAC.

### "ImportError: No module named 'winsdk'"

WGC is only available on Windows 10 1903+.  The engine automatically falls
back to DXGI or MSS if WGC is unavailable — no action needed.

### Debug mode

```bash
python main.py --debug
# or
AMBILIGHT_LOG_LEVEL=DEBUG python main.py
```

Logs include per-frame RGB values, zone analysis results, and timing data.

---

## Environment Variables

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

## Colour Modes Reference

| Mode | Quality | Speed | Best for |
|---|---|---|---|
| `average` | ★★ | ★★★★★ | Static scenes, low-power |
| `edges` | ★★★ | ★★★★ | Wide-format video with bars |
| `dominant` | ★★★★ | ★★★ | Animated content |
| `kmeans` | ★★★★★ | ★★ | Accuracy-critical setups |
| `saturation_weighted` | ★★★★★ | ★★★★ | **Default — best balance** |

---

## License

MIT — use freely, contribute back.
