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
import logging.handlers
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
        existing = getattr(sys, name, None)
        if existing is not None:
            # A real stream is already wired (e.g. by the Electron supervisor).
            # Force UTF-8 with replacement so a log line containing a non-cp1252
            # character (the "->" we just dropped, an emoji/CJK app name, etc.)
            # can never raise UnicodeEncodeError and corrupt the handler.
            try:
                existing.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            continue
        try:
            stream = os.fdopen(fd, "w", buffering=1, encoding="utf-8", errors="replace")
        except OSError:
            stream = open(os.devnull, "w", encoding="utf-8", errors="replace")
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

    from ambilight import __version__ as app_version
    logger.info("[Service] Ambilight Desktop service v%s", app_version)

    # Load .env (dev convenience / installed-build override) BEFORE anything reads
    # the environment, so non-secret config like AMBILIGHT_GITHUB_CLIENT_ID is
    # available to the integration. Never overrides an already-set env var.
    from ambilight import paths as _paths
    _paths.load_env_files()

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

    # The pipeline worker owns the rotating ambilight.log (single writer — avoids a
    # multi-process rotation race). But the notification listener + service run in
    # THIS process, so their [Notify] logs never reached the in-app viewer. Give
    # this process its OWN rotating file (sibling ambilight.notify.log) that the
    # Electron Logs page merges in; this process is its only writer, so no race.
    try:
        notify_log = os.path.join(os.path.dirname(cfg.logging.file), "ambilight.notify.log")
        fh = logging.handlers.RotatingFileHandler(
            notify_log,
            maxBytes=getattr(cfg.logging, "max_bytes", 20_971_520),
            backupCount=getattr(cfg.logging, "backup_count", 10),
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logging.getLogger().addHandler(fh)
        logger.info("[Service] Notification log: %s", notify_log)
    except Exception as exc:  # pragma: no cover - never block boot on logging
        logger.warning("[Service] Could not attach notification log file: %s", exc)

    # Resolve cache_file to an absolute path for the same reason: the service is
    # installed under Program Files (read-only). A relative "device_cache.json"
    # would trigger Permission Denied on first write, silently breaking MAC-based
    # device re-discovery after a DHCP IP change.
    def _resolve_cache(path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(ambilight_dir, path)

    cfg.device.cache_file = _resolve_cache(cfg.device.cache_file)
    for dev in cfg.devices:
        if isinstance(dev, dict) and not os.path.isabs(dev.get("cache_file", "")):
            dev["cache_file"] = _resolve_cache(dev.get("cache_file", "device_cache.json"))

    if args.host != DEFAULT_HOST:
        logger.warning(
            "[Service] Binding to non-loopback host %s — the API has no network "
            "authentication beyond a local token; expose with care.",
            args.host,
        )

    try:
        import threading
        import time
        import uvicorn
        # Import the app object directly (rather than the "module:attr" string)
        # so a frozen PyInstaller build statically bundles ambilight.api_server
        # and its transitive imports. We don't use reload/multiple workers, so
        # passing the object is equivalent to the string form.
        from ambilight.api_server import app
        from ambilight.parent_watchdog import start_parent_watchdog
        logger.info("[Service] Starting uvicorn on %s:%s (frozen=%s)",
                    args.host, args.port, getattr(sys, "frozen", False))

        # Build the server explicitly so the parent watchdog can ask it to shut
        # down *gracefully* (fires the API shutdown event → stops the pipeline →
        # turns the strip off) when the Electron shell is force-quit, instead of
        # leaving an orphaned service behind.
        config = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level=cfg.logging.level.lower(),
        )
        server = uvicorn.Server(config)

        def _on_parent_exit() -> None:
            server.should_exit = True
            # Failsafe: if graceful shutdown stalls (e.g. a wedged device send),
            # hard-exit so the service can never linger after the shell is gone.
            def _force() -> None:
                time.sleep(8.0)
                logger.warning("[Service] Graceful shutdown timed out after parent exit; forcing exit.")
                os._exit(0)
            threading.Thread(target=_force, name="watchdog-failsafe", daemon=True).start()

        start_parent_watchdog(_on_parent_exit)
        server.run()
    except Exception as exc:  # pragma: no cover - fatal boot failure
        logging.getLogger(__name__).critical(
            "[Service] Fatal error: %s", exc, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
