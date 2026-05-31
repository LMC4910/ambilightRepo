"""
Configuration Module
====================
Manages YAML-based configuration with validation, type-safe access,
and sensible production defaults.

All configuration is accessible via a singleton Config object that is
initialized once from disk and then shared across all modules.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed sub-config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CaptureConfig:
    method: str = "wgc"           # wgc | dxgi | mss
    monitor_index: int = 0        # 0 = primary
    fps_target: int = 30
    analysis_width: int = 80
    analysis_height: int = 45


@dataclass
class DeviceConfig:
    ip: str = "192.168.1.29"
    port: int = 5577
    mac: str = ""                 # preferred over IP when set
    subnet: str = "192.168.1."
    connect_timeout: float = 2.0
    send_timeout: float = 1.0
    reconnect_interval: float = 5.0
    discovery_timeout: float = 0.5
    cache_file: str = "device_cache.json"


@dataclass
class ZoneConfig:
    top: int = 7
    bottom: int = 7
    left: int = 4
    right: int = 4


@dataclass
class ColorConfig:
    mode: str = "saturation_weighted"  # average | edges | dominant | kmeans | saturation_weighted
    kmeans_clusters: int = 3
    ignore_black_threshold: int = 30   # pixels darker than this (all channels) are ignored
    ignore_white_threshold: int = 225  # pixels brighter than this (all channels) are ignored
    saturation_weight_power: float = 2.0
    min_saturation: float = 0.05


@dataclass
class SmoothingConfig:
    enabled: bool = True
    base_alpha: float = 0.15          # base EMA coefficient (lower = smoother)
    adaptive_fast_threshold: int = 60  # colour delta above which we switch to fast mode
    adaptive_fast_alpha: float = 0.55  # EMA coefficient in fast mode
    min_change: int = 2               # skip update if max channel delta < this


@dataclass
class GpuConfig:
    enabled: bool = True
    prefer: str = "cupy"             # cupy | opencv_cuda | torch | none
    fallback_to_cpu: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/ambilight.log"
    max_bytes: int = 5_242_880       # 5 MB
    backup_count: int = 3
    show_fps: bool = True
    fps_interval: float = 5.0        # seconds between FPS log lines


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    zones: ZoneConfig = field(default_factory=ZoneConfig)
    color: ColorConfig = field(default_factory=ColorConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    gpu: GpuConfig = field(default_factory=GpuConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """
    Recursively instantiate a dataclass from a dictionary.

    Nested dictionaries are converted to nested dataclasses where the field
    type annotation is itself a dataclass.
    """
    import dataclasses
    import inspect

    if not dataclasses.is_dataclass(cls):
        return data

    field_types = {f.name: f.type for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in field_types:
            logger.warning("Unknown config key '%s' in section '%s'; ignoring.", key, cls.__name__)
            continue
        type_hint = field_types[key]
        # Resolve string annotations (e.g. from __future__ annotations)
        if isinstance(type_hint, str):
            frame = inspect.currentframe()
            try:
                resolved = eval(type_hint, frame.f_back.f_globals if frame else {})  # noqa: S307
            except Exception:
                resolved = None
            type_hint = resolved
        if (
            type_hint is not None
            and dataclasses.is_dataclass(type_hint)
            and isinstance(value, dict)
        ):
            kwargs[key] = _dict_to_dataclass(type_hint, value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


class ConfigManager:
    """
    Singleton configuration manager.

    Load once with ``ConfigManager.load(path)``; access the populated
    ``AppConfig`` via ``ConfigManager.get()``.
    """

    _instance: AppConfig | None = None

    @classmethod
    def load(cls, path: str | Path = "configuration.yaml") -> AppConfig:
        """
        Load configuration from *path*, merging with built-in defaults.

        Parameters
        ----------
        path:
            Filesystem path to the YAML configuration file.  If the file does
            not exist a warning is emitted and default values are used.
        """
        path = Path(path)
        raw: dict[str, Any] = {}

        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                logger.error("Configuration file is not a YAML mapping; using defaults.")
            else:
                raw = loaded
        else:
            logger.warning("Configuration file '%s' not found; using defaults.", path)

        # Build a typed AppConfig from raw dict
        config = _dict_to_dataclass(AppConfig, raw)
        if not isinstance(config, AppConfig):
            config = AppConfig()

        cls._instance = config
        return config

    @classmethod
    def get(cls) -> AppConfig:
        """
        Return the loaded configuration, loading defaults if never called.
        """
        if cls._instance is None:
            cls._instance = AppConfig()
        return cls._instance
