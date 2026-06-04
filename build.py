"""
build.py
========
Cross-platform build script for Ambilight Desktop. Produces, for the host OS:

  1. A PyInstaller ``--onedir`` bundle of the Python service, named
     ``ambilight-service`` (the name the Electron shell looks for under
     ``resources/service/``).
  2. The Electron installer for the host OS via electron-builder
     (NSIS on Windows, DMG on macOS, AppImage + deb on Linux).

Usage:
    python build.py              # service + UI for the current OS
    python build.py --service    # service only
    python build.py --ui         # UI only

Requirements: Python 3.11+ with PyInstaller; Node 20+ with pnpm.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SERVICE_DIST = DIST / "service"
UI_DIR = ROOT / "ui"

SERVICE_NAME = "ambilight-service"
SYSTEM = platform.system()  # Windows | Darwin | Linux


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n{'=' * 60}\n  Running: {' '.join(cmd)}\n  CWD:     {cwd or ROOT}\n{'=' * 60}\n")
    result = subprocess.run(cmd, cwd=str(cwd or ROOT))
    if result.returncode != 0:
        print(f"\n[FATAL] Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def _check_tool(name: str, version_flag: str = "--version") -> None:
    try:
        subprocess.run([name, version_flag], capture_output=True, check=True)
    except FileNotFoundError:
        print(f"[FATAL] Required tool not found on PATH: {name}")
        sys.exit(1)


def build_service() -> None:
    print("\n[1/2] Building Python service with PyInstaller…")
    _check_tool("pyinstaller")

    if SERVICE_DIST.exists():
        shutil.rmtree(SERVICE_DIST)
    SERVICE_DIST.mkdir(parents=True, exist_ok=True)

    hidden_imports = [
        "--hidden-import=mss",
        "--hidden-import=numpy",
        "--hidden-import=cv2",
        "--hidden-import=yaml",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
    ]
    for opt in ("dxcam", "cupy", "winsdk", "comtypes", "soundcard", "windows_capture"):
        try:
            __import__(opt)
            hidden_imports.append(f"--hidden-import={opt}")
        except ImportError:
            pass

    # Packages with compiled extensions / bundled data files need --collect-all
    # so their native modules ship, not just the Python import graph.
    collect_all: list[str] = []
    for pkg in ("windows_capture", "soundcard"):
        try:
            __import__(pkg)
            collect_all += ["--collect-all", pkg]
        except ImportError:
            pass

    sep = os.pathsep  # ; on Windows, : elsewhere
    _run([
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--name", SERVICE_NAME,
        "--distpath", str(SERVICE_DIST),
        "--specpath", str(DIST / "build_spec"),
        "--workpath", str(DIST / "build_work"),
        "--add-data", f"{ROOT / 'configuration.yaml'}{sep}.",
        "--add-data", f"{ROOT / 'profiles'}{sep}profiles",
        # Collect the whole package so conditionally/dynamically imported
        # submodules (capture backends, api_server referenced via uvicorn) ship.
        "--collect-submodules", "ambilight",
        *collect_all,
        *hidden_imports,
        str(ROOT / "service_entry.py"),
    ])
    print(f"\n[OK] Service built: {SERVICE_DIST / SERVICE_NAME}")


def build_ui() -> None:
    print("\n[2/2] Building Electron UI with electron-builder…")
    _check_tool("pnpm")

    _run(["pnpm", "install", "--frozen-lockfile"], cwd=UI_DIR)
    _run(["pnpm", "run", "build"], cwd=UI_DIR)

    target_flag = {"Windows": "--win", "Darwin": "--mac", "Linux": "--linux"}.get(SYSTEM, "--linux")
    _run(["pnpm", "exec", "electron-builder", target_flag], cwd=UI_DIR)
    print(f"\n[OK] UI built. See {UI_DIR / 'release'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Ambilight Desktop (cross-platform)")
    parser.add_argument("--service", action="store_true", help="Build service only")
    parser.add_argument("--ui", action="store_true", help="Build UI only")
    args = parser.parse_args()

    build_all = not args.service and not args.ui
    if build_all or args.service:
        build_service()
    if build_all or args.ui:
        build_ui()

    if build_all:
        print("\n" + "=" * 60)
        print("  BUILD COMPLETE")
        print(f"  Service: {SERVICE_DIST / SERVICE_NAME}")
        print(f"  UI:      {UI_DIR / 'release'}")
        print("=" * 60)


if __name__ == "__main__":
    main()
