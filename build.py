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


def build_service(gpu: bool = False) -> None:
    print(f"\n[1/2] Building Python service with PyInstaller ({'GPU' if gpu else 'lean CPU'})…")
    _check_tool("pyinstaller")

    if SERVICE_DIST.exists():
        shutil.rmtree(SERVICE_DIST)
    SERVICE_DIST.mkdir(parents=True, exist_ok=True)

    hidden_imports = [
        "--hidden-import=mss",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--hidden-import=yaml",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
    ]
    # Probe availability WITHOUT importing — importing winsdk/comtypes/
    # windows_capture here would fight over the COM apartment and crash the build.
    import importlib.util
    def _available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except Exception:
            return False

    # Always-bundled optional native deps (capture backends + audio + WGC).
    optional = ["dxcam", "winsdk", "comtypes", "soundcard", "windows_capture"]
    collect_all: list[str] = []
    for pkg in ("windows_capture", "soundcard"):
        if _available(pkg):
            collect_all += ["--collect-all", pkg]

    # Lean build: drop the heavy GPU stack (CuPy ~118 MB + CUDA ~86 MB) and
    # OpenCV (~99 MB; resize falls back to Pillow). Also drop obvious dead weight.
    # GPU build (--gpu) re-includes CuPy + OpenCV for users who want it.
    excludes = ["tkinter", "_tkinter", "lib2to3", "pydoc_data", "matplotlib", "PyQt5", "PySide2"]
    if gpu:
        optional += ["cupy", "cv2", "torch"]
        for pkg in ("cupy", "cv2"):
            if _available(pkg):
                collect_all += ["--collect-all", pkg]
    else:
        excludes += ["cupy", "cupyx", "cupy_backends", "torch", "cv2", "nvidia"]

    for opt in optional:
        if _available(opt):
            hidden_imports.append(f"--hidden-import={opt}")

    exclude_args: list[str] = []
    for mod in excludes:
        exclude_args += ["--exclude-module", mod]

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
        *exclude_args,
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
    parser.add_argument("--gpu", action="store_true",
                        help="Bundle CuPy/CUDA + OpenCV (large GPU build). Default is lean CPU-only.")
    args = parser.parse_args()

    build_all = not args.service and not args.ui
    if build_all or args.service:
        build_service(gpu=args.gpu)
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
