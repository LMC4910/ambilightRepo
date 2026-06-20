# ambilight package

# Canonical version for the Python background service. This MUST match the
# Electron app version in ui/package.json — package.json drives the installer
# and the electron-updater feed, and build.py verifies the two agree before
# building the service binary (see build.py:_check_version_sync). Bump the
# VERSION file at the repo root to update both the Python and Electron versions
# simultaneously (semver: patch for fixes, minor for features, major for breaking changes).

from pathlib import Path

_version_file = Path(__file__).resolve().parent.parent / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip()
