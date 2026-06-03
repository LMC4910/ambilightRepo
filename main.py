"""
Ambilight Engine — Entry Point
==============================
Run with:

    python main.py
    python main.py --config /path/to/configuration.yaml
    python main.py --discover          # scan network only
    python main.py --list-monitors     # print monitor indices

Environment overrides
---------------------
Set environment variables to override YAML config at runtime:

    AMBILIGHT_IP=192.168.1.50 python main.py
    AMBILIGHT_MODE=kmeans python main.py
    AMBILIGHT_LOG_LEVEL=DEBUG python main.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure the project root is on sys.path when run directly
sys.path.insert(0, os.path.dirname(__file__))

from ambilight.config import AppConfig, ConfigManager
from ambilight.discovery import DeviceDiscovery, DeviceScanner
from ambilight.pipeline import AmbilightPipeline


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _list_monitors() -> None:
    """Print available monitor indices detected by MSS."""
    try:
        import mss  # type: ignore[import-untyped]
        with mss.mss() as sct:
            real = sct.monitors[1:]
            print(f"{'Index':<6}  {'Resolution':<18}  {'Position'}")
            for i, mon in enumerate(real):
                res = f"{mon['width']}×{mon['height']}"
                pos = f"({mon['left']}, {mon['top']})"
                print(f"{i:<6}  {res:<18}  {pos}")
    except ImportError:
        print("[ERROR] mss is not installed.  Run: pip install mss")


def _run_discovery(cfg: AppConfig) -> None:
    """Perform a device scan and print results."""
    d = cfg.device
    scanner = DeviceScanner(subnet=d.subnet, connect_timeout=d.discovery_timeout)
    devices = scanner.scan()
    if not devices:
        print("[INFO] No MagicHome devices found.")
        return
    print(f"\nFound {len(devices)} device(s):\n")
    for dev in devices:
        print(f"  IP  : {dev.ip}")
        print(f"  MAC : {dev.mac or 'unknown'}")
        print()


# ---------------------------------------------------------------------------
# Environment overrides
# ---------------------------------------------------------------------------

def _apply_env_overrides(cfg: AppConfig) -> AppConfig:
    """
    Apply optional environment variable overrides to a loaded config.

    Supported variables
    -------------------
    AMBILIGHT_IP          → cfg.device.ip
    AMBILIGHT_MAC         → cfg.device.mac
    AMBILIGHT_MODE        → cfg.color.mode
    AMBILIGHT_FPS         → cfg.capture.fps_target
    AMBILIGHT_LOG_LEVEL   → cfg.logging.level
    AMBILIGHT_MONITOR     → cfg.capture.monitor_index
    AMBILIGHT_GPU         → cfg.gpu.prefer (or "none" to disable)
    """
    if val := os.environ.get("AMBILIGHT_IP"):
        cfg.device.ip = val
    if val := os.environ.get("AMBILIGHT_MAC"):
        cfg.device.mac = val
    if val := os.environ.get("AMBILIGHT_MODE"):
        cfg.color.mode = val
    if val := os.environ.get("AMBILIGHT_FPS"):
        try:
            cfg.capture.fps_target = int(val)
        except ValueError:
            pass
    if val := os.environ.get("AMBILIGHT_LOG_LEVEL"):
        cfg.logging.level = val
    if val := os.environ.get("AMBILIGHT_MONITOR"):
        try:
            cfg.capture.monitor_index = int(val)
        except ValueError:
            pass
    if val := os.environ.get("AMBILIGHT_GPU"):
        cfg.gpu.prefer = val
        cfg.gpu.enabled = val.lower() != "none"
    return cfg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production-grade Ambilight engine for MagicHome LED controllers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default="configuration.yaml",
        metavar="PATH",
        help="Path to YAML configuration file (default: configuration.yaml)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Scan network for MagicHome devices and exit.",
    )
    parser.add_argument(
        "--list-monitors",
        action="store_true",
        help="List available monitor indices and exit.",
    )
    parser.add_argument(
        "--ip",
        metavar="IP",
        help="Override device IP from config.",
    )
    parser.add_argument(
        "--mode",
        choices=["average", "edges", "dominant", "kmeans", "saturation_weighted"],
        help="Override colour analysis mode.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Set log level to DEBUG.",
    )

    args = parser.parse_args()

    # Load config
    cfg = ConfigManager.load(args.config)
    cfg = _apply_env_overrides(cfg)

    # CLI argument overrides
    if args.ip:
        cfg.device.ip = args.ip
    if args.mode:
        cfg.color.mode = args.mode
    if args.debug:
        cfg.logging.level = "DEBUG"

    # Sub-commands
    if args.list_monitors:
        _list_monitors()
        return

    if args.discover:
        # Minimal logging for discovery mode
        logging.basicConfig(level=logging.WARNING)
        _run_discovery(cfg)
        return

    # Full pipeline (via FastAPI Server)
    try:
        import uvicorn
        uvicorn.run("ambilight.api_server:app", host="127.0.0.1", port=7826, log_level="info")
    except Exception as exc:
        logging.getLogger(__name__).critical(
            "Server fatal error: %s", exc, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
