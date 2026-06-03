"""
Auto-start Registration (FR-SVC-01)
===================================
Registers the Ambilight background service to start automatically on login,
per-user and without admin rights (NFR-S-05):

* Windows — a ``.cmd`` launcher in the user's Startup folder.
* macOS    — a launchd agent in ``~/Library/LaunchAgents``.
* Linux    — a systemd *user* unit in ``~/.config/systemd/user``.

Used by the installer / first-run wizard, or directly::

    python -m ambilight.autostart install      # uses `python -m ambilight.service`
    python -m ambilight.autostart install --command "/path/to/ambilight-service"
    python -m ambilight.autostart remove
    python -m ambilight.autostart status
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ID = "com.ambilight.service"
SYSTEM = platform.system()


def _default_command() -> str:
    """Best-effort command that launches the service in the current install."""
    # Frozen bundle: the running executable IS the service binary.
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m ambilight.service'


# ---------------------------------------------------------------------------
# Windows — Startup folder launcher
# ---------------------------------------------------------------------------

def _win_startup_path() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "AmbilightService.cmd"


def _win_install(command: str) -> None:
    target = _win_startup_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # `start "" /min` launches detached and minimised so no console lingers.
    target.write_text(f'@echo off\r\nstart "" /min {command}\r\n', encoding="utf-8")
    logger.info("[Autostart] Installed Windows startup launcher: %s", target)


def _win_remove() -> None:
    target = _win_startup_path()
    if target.exists():
        target.unlink()
        logger.info("[Autostart] Removed Windows startup launcher.")


def _win_status() -> bool:
    return _win_startup_path().exists()


# ---------------------------------------------------------------------------
# macOS — launchd agent
# ---------------------------------------------------------------------------

def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def _mac_install(command: str) -> None:
    # Split the command into program + args for ProgramArguments.
    import shlex
    args = shlex.split(command)
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{APP_ID}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
"""
    path = _mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "load", str(path)], check=False)
    logger.info("[Autostart] Installed launchd agent: %s", path)


def _mac_remove() -> None:
    path = _mac_plist_path()
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], check=False)
        path.unlink()
        logger.info("[Autostart] Removed launchd agent.")


def _mac_status() -> bool:
    return _mac_plist_path().exists()


# ---------------------------------------------------------------------------
# Linux — systemd user unit
# ---------------------------------------------------------------------------

def _linux_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "ambilight.service"


def _linux_install(command: str) -> None:
    unit = f"""[Unit]
Description=Ambilight Desktop background service
After=graphical-session.target

[Service]
ExecStart={command}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    path = _linux_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "ambilight.service"], check=False)
    logger.info("[Autostart] Installed systemd user unit: %s", path)


def _linux_remove() -> None:
    path = _linux_unit_path()
    if path.exists():
        subprocess.run(["systemctl", "--user", "disable", "--now", "ambilight.service"], check=False)
        path.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        logger.info("[Autostart] Removed systemd user unit.")


def _linux_status() -> bool:
    return _linux_unit_path().exists()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_DISPATCH = {
    "Windows": (_win_install, _win_remove, _win_status),
    "Darwin": (_mac_install, _mac_remove, _mac_status),
    "Linux": (_linux_install, _linux_remove, _linux_status),
}


def install(command: str | None = None) -> None:
    cmd = command or _default_command()
    handlers = _DISPATCH.get(SYSTEM)
    if not handlers:
        raise RuntimeError(f"Auto-start not supported on platform: {SYSTEM}")
    handlers[0](cmd)


def remove() -> None:
    handlers = _DISPATCH.get(SYSTEM)
    if handlers:
        handlers[1]()


def status() -> bool:
    handlers = _DISPATCH.get(SYSTEM)
    return bool(handlers and handlers[2]())


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="ambilight.autostart", description="Manage Ambilight auto-start on login.")
    parser.add_argument("action", choices=["install", "remove", "status"])
    parser.add_argument("--command", help="Command to launch the service (default: this Python + -m ambilight.service).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.action == "install":
        install(args.command)
    elif args.action == "remove":
        remove()
    else:
        print(f"auto-start enabled: {status()}")


if __name__ == "__main__":
    main()
