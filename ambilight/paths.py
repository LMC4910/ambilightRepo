"""
Path helpers
============
Resolve the per-user data directory (``~/.ambilight``) and the location of
data files that ship *with* the app (``configuration.yaml``, ``profiles/``).

In a frozen PyInstaller build the bundled data lives under ``sys._MEIPASS``
(``--add-data`` payloads), and the install directory (e.g.
``C:\\Program Files\\Ambilight Desktop``) is read-only — so anything the service
needs to write (config, profiles, logs, cache) must live under the user data
dir. In development the bundled data is the repo root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running as a PyInstaller-frozen binary."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> Path:
    """Per-user, writable data dir (created on demand): ``~/.ambilight``."""
    d = Path(os.path.expanduser("~")) / ".ambilight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(name: str) -> str:
    """Absolute path to a data file bundled with the app.

    Frozen: under ``sys._MEIPASS`` (``_internal`` for onedir builds).
    Dev: the repo root (two levels up from this file).
    """
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)
