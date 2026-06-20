# ambilight package

# Canonical version for the Python background service. This MUST match the
# Electron app version in ui/package.json — package.json drives the installer
# and the electron-updater feed, and build.py verifies the two agree before
# building the service binary (see build.py:_check_version_sync). Bump both
# together on every release (semver: patch for fixes, minor for features, major
# for breaking changes).
__version__ = "1.0.2"
