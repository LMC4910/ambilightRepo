"""
Service Entry Point
===================
Boots the Ambilight background service:

    config → env overrides → logging → uvicorn (which on startup wires up the
    auth token, event bus, platform monitor and pipeline controller — see
    ``ambilight.api_server``).

Run with::

    python -m ambilight.service
    python -m ambilight.service --config /path/to/configuration.yaml
    AMBILIGHT_PORT=7826 python -m ambilight.service

The legacy ``main.py`` CLI remains the way to run one-off ``--discover`` /
``--list-monitors`` commands and the in-terminal pipeline; this module is what
the installer / Electron shell launches as a long-lived service.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure the project root is importable when launched as a frozen binary or
# from an arbitrary working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ambilight.config import ConfigManager
from main import _apply_env_overrides  # reuse the existing env-override logic

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"  # NFR-S-01: bind to loopback only
DEFAULT_PORT = 7826


def _ensure_std_streams() -> None:
    """Guarantee ``sys.stdout``/``sys.stderr`` are writable before logging starts.

    ``python -m ambilight.service`` under ``pythonw.exe`` (the windowless dev
    spawn) — and any no-console launch — has both streams set to ``None``, which
    makes ``logging.basicConfig(stream=sys.stdout)`` and uvicorn crash. The
    Electron supervisor wires real file handles to fd 1/2, so rebind to those;
    fall back to the null device when no descriptor is available. (The frozen
    binary also applies this in ``service_entry.py`` for spawned workers.)
    """
    import os
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name, None) is not None:
            continue
        try:
            stream = os.fdopen(fd, "w", buffering=1)
        except OSError:
            stream = open(os.devnull, "w")
        setattr(sys, name, stream)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ambilight.service",
        description="Ambilight Desktop background service (REST + WebSocket).",
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("AMBILIGHT_CONFIG", "configuration.yaml"),
        metavar="PATH",
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("AMBILIGHT_HOST", DEFAULT_HOST),
        help="Bind address (default 127.0.0.1 — loopback only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AMBILIGHT_PORT", DEFAULT_PORT)),
        help="Bind port (default 7826).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _ensure_std_streams()
    # Give the parent/API process a stream handler up front. The rotating FILE
    # handler is owned solely by the pipeline worker (single writer — avoids a
    # multi-process rotation race); this handler just makes the parent's boot
    # steps and any fatal-error traceback land on stdout/stderr, which the
    # Electron shell now captures to ~/.ambilight/logs/service.out.log. Without
    # it, a parent-side crash before the worker starts is completely silent.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # 1. Resolve the config path. In an installed (frozen) build the working
    #    directory is the read-only install dir, so the canonical config lives at
    #    ~/.ambilight/configuration.yaml — seeded from the bundled default on
    #    first run. An explicit --config / AMBILIGHT_CONFIG always wins. In dev
    #    the existing repo-relative path is kept.
    from ambilight import paths
    ambilight_dir = str(paths.user_data_dir())
    explicit = args.config != "configuration.yaml"
    config_path = args.config
    if paths.is_frozen() and not explicit:
        user_config = os.path.join(ambilight_dir, "configuration.yaml")
        if not os.path.exists(user_config):
            bundled = paths.resource_path("configuration.yaml")
            if os.path.exists(bundled):
                import shutil
                shutil.copyfile(bundled, user_config)
                logger.info("[Service] Seeded user config from bundled default: %s", user_config)
        config_path = user_config

    # 2. Load + normalise configuration BEFORE the app starts so the singleton
    #    is populated for both this process and any spawned pipeline workers.
    cfg = ConfigManager.load(config_path)
    _apply_env_overrides(cfg)
    logger.info("[Service] Config loaded from %s", ConfigManager.loaded_path())

    # Anchor runtime artifacts under the per-user data dir so the Electron UI
    # (which reads ~/.ambilight/logs/ambilight.log) finds them no matter what
    # working directory the service was launched from.
    if not os.path.isabs(cfg.logging.file):
        cfg.logging.file = os.path.join(ambilight_dir, cfg.logging.file)
    os.makedirs(os.path.dirname(cfg.logging.file), exist_ok=True)

    if args.host != DEFAULT_HOST:
        logger.warning(
            "[Service] Binding to non-loopback host %s — the API has no network "
            "authentication beyond a local token; expose with care.",
            args.host,
        )

    try:
        import uvicorn
        # Import the app object directly (rather than the "module:attr" string)
        # so a frozen PyInstaller build statically bundles ambilight.api_server
        # and its transitive imports. We don't use reload/multiple workers, so
        # passing the object is equivalent to the string form.
        from ambilight.api_server import app
        logger.info("[Service] Starting uvicorn on %s:%s (frozen=%s)",
                    args.host, args.port, getattr(sys, "frozen", False))
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=cfg.logging.level.lower(),
        )
    except Exception as exc:  # pragma: no cover - fatal boot failure
        logging.getLogger(__name__).critical(
            "[Service] Fatal error: %s", exc, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
