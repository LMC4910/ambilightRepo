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


def load_env_files() -> None:
    """Best-effort: load ``KEY=VALUE`` pairs from ``.env`` files into ``os.environ``.

    A developer convenience (so non-secret config like the GitHub OAuth
    ``client_id`` can live in a gitignored ``.env`` instead of being hard-coded)
    and an override hook for installed builds (drop ``~/.ambilight/.env``).
    Values already present in the environment are **never** overwritten, so a
    real env var or CI injection always wins. Checks, in order: the bundled /
    repo-root ``.env``, the per-user data dir, and the current working directory.
    """
    candidates = []
    try:
        candidates.append(Path(resource_path(".env")))
    except Exception:
        pass
    try:
        candidates.append(user_data_dir() / ".env")
    except Exception:
        pass
    try:
        candidates.append(Path(os.getcwd()) / ".env")
    except Exception:
        pass

    seen: set[str] = set()
    for path in candidates:
        try:
            key_path = str(path.resolve())
        except Exception:
            key_path = str(path)
        if key_path in seen:
            continue
        seen.add(key_path)
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                if s.lower().startswith("export "):
                    s = s[len("export "):].lstrip()
                key, _, val = s.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        except Exception:
            continue
