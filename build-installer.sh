#!/usr/bin/env bash
# ===========================================================================
#  Ambilight Desktop - one-line installer build (macOS / Linux)
# ===========================================================================
#  Builds the PyInstaller service bundle AND the electron-builder installer
#  (DMG on macOS, AppImage + deb on Linux) in one shot (wraps build.py).
#
#  Usage:
#    ./build-installer.sh             full build  -> ui/release/
#    ./build-installer.sh --service   service binary only
#    ./build-installer.sh --ui        app + installer only (service must exist)
#    ./build-installer.sh --gpu       bundle CuPy/CUDA + OpenCV (large GPU build)
# ===========================================================================
set -euo pipefail
cd "$(dirname "$0")"
exec python build.py "$@"
