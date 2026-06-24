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

# Supported device protocols (selects the LED driver via devices/factory.py).
_KNOWN_PROTOCOLS = {"magichome", "wled"}

# ---------------------------------------------------------------------------
# Typed sub-config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HdrConfig:
    # auto = tone-map only when the display reports HDR enabled; on = always;
    # off = never. Tone-map runs on the downscaled analysis frame.
    mode: str = "auto"            # auto | on | off
    exposure: float = 1.0         # linear gain before the contrast curve
    contrast: float = 1.15        # S-curve strength about mid-grey (1.0 = none)
    saturation_recovery: float = 1.5  # chroma scale about luma (1.0 = none)


@dataclass
class CaptureConfig:
    method: str = "wgc"           # wgc | dxgi | mss
    monitor_index: int = 0        # 0 = primary (fallback when monitor_id is unset)
    monitor_id: str = ""          # stable monitor identity (EDID/gdi_name/pos); see monitors.py
    fps_target: int = 30
    analysis_width: int = 80
    analysis_height: int = 45
    hdr: HdrConfig = field(default_factory=HdrConfig)


@dataclass
class DeviceConfig:
    ip: str = "192.168.1.29"
    port: int = 5577
    mac: str = "30:3a:29:00:0c:00"                 # preferred over IP when set
    subnet: str = "192.168.1."
    connect_timeout: float = 2.0
    send_timeout: float = 1.0
    reconnect_interval: float = 5.0
    discovery_timeout: float = 0.5
    cache_file: str = "device_cache.json"
    led_count: int = 30           # LEDs per strip (addressable devices only)
    monitor_index: int = 0        # which monitor this device mirrors (fallback for monitor_id)
    monitor_id: str = ""          # stable monitor identity (preferred over monitor_index)
    name: str = ""                # friendly label (defaults to IP)
    protocol: str = "magichome"   # magichome | wled — selects the LED driver
    enabled: bool = True          # include this device in the pipeline


@dataclass
class ZoneConfig:
    top: int = 7
    bottom: int = 7
    left: int = 4
    right: int = 4
    edge_fraction: float = 0.25   # strip thickness as a fraction of frame H/W


@dataclass
class ColorConfig:
    mode: str = "saturation_weighted"  # average | edges | dominant | kmeans | saturation_weighted
    kmeans_clusters: int = 3
    ignore_black_threshold: int = 30   # pixels darker than this (all channels) are ignored
    ignore_white_threshold: int = 225  # pixels brighter than this (all channels) are ignored
    saturation_weight_power: float = 2.0
    min_saturation: float = 0.05
    vibrance: float = 1.0              # post-analysis chroma boost (1.0 = off)


@dataclass
class SmoothingConfig:
    enabled: bool = True
    base_alpha: float = 0.15          # base EMA coefficient (lower = smoother)
    adaptive_fast_threshold: int = 60  # colour delta above which we switch to fast mode
    adaptive_fast_alpha: float = 0.55  # EMA coefficient in fast mode
    min_change: int = 2               # skip update if max channel delta < this


@dataclass
class GradientConfig:
    enabled: bool = True             # use addressable gradient output when supported
    mode: str = "screen_matched"     # linear | radial | ambient | screen_matched
    gamma: float = 2.2


@dataclass
class GpuConfig:
    enabled: bool = True
    prefer: str = "cupy"             # cupy | opencv_cuda | torch | none
    fallback_to_cpu: bool = True


@dataclass
class EffectsConfig:
    plugins_dir: str = ""            # default resolved to ~/.ambilight/plugins at load
    schedule: list = field(default_factory=list)  # [{effect, params, window}]
    # Per-mode user params, e.g. {"rainbow": {"speed": 1.0},
    # "static": {"r":255,"g":0,"b":0}, "custom": {"colors": [[r,g,b],...], "speed": 1.0}}
    params: dict = field(default_factory=dict)


@dataclass
class AutoProfileConfig:
    """Auto-switch the active profile based on the foreground application (FR-PROF-07)."""
    enabled: bool = False
    poll_interval: float = 2.0       # seconds between foreground checks
    default_profile: str = ""        # applied when no rule matches ("" = leave as-is)
    rules: list = field(default_factory=list)  # ordered [{match: "game.exe", profile: "gaming"}]


@dataclass
class LoggingConfig:
    level: str = "INFO"              # console / root verbosity
    file_level: str = "INFO"         # on-disk verbosity (independent of console)
    file: str = "logs/ambilight.log"
    max_bytes: int = 20_971_520      # 20 MB per file
    backup_count: int = 10           # → ~220 MB hard ceiling, then oldest dropped
    show_fps: bool = True
    fps_interval: float = 5.0        # seconds between FPS log lines


@dataclass
class MqttConfig:
    # Smart-home MQTT bridge + Home Assistant discovery (off by default).
    enabled: bool = False
    broker: str = ""              # broker host/IP; blank disables the bridge
    port: int = 1883
    username: str = ""
    password: str = ""            # write-only: moved to the OS keyring on save,
                                  # never persisted to configuration.yaml
    tls: bool = False
    base_topic: str = "ambilight"
    ha_discovery: bool = False    # publish Home Assistant MQTT discovery configs
    device_id: str = ""           # blank → hostname (stable HA device identifier)


@dataclass
class NotificationConfig:
    """Flash the LEDs when an OS notification arrives (Notification Flash).

    Helps the user notice notifications they would otherwise miss in fullscreen,
    during Do Not Disturb / Focus Assist, or while the screen is locked. The
    flash colour defaults to the originating app's icon dominant colour, with
    per-app overrides and keyword rules (the latter for Phone Link / forwarded
    phone notifications, which Windows reports as coming from "Phone Link").
    """
    enabled: bool = False
    default_color: list = field(default_factory=lambda: [255, 255, 255])  # [r,g,b] fallback
    brightness: float = 1.0          # 0..1 scale applied to the flash colour
    blink_count: int = 2             # number of on/off blinks
    on_ms: int = 180                 # per-blink on duration
    off_ms: int = 120                # per-blink gap
    color_mode: str = "icon"         # "icon" (app logo colour) | "fixed" (always default_color)
    suppress_during_dnd: bool = False  # default: STILL flash during DND / Focus Assist
    flash_when_locked: bool = True   # default: STILL flash while the screen is locked / asleep
    dedup_window_s: float = 5.0      # drop identical (app,title,body) within this window
    min_flash_interval_s: float = 1.5  # throttle/coalesce notification bursts
    # Per-app custom colours: {app_id_or_name: [r,g,b]}
    app_overrides: dict = field(default_factory=dict)
    # Keyword→colour rules (Phone Link / forwarded), ordered:
    #   [{keyword: "whatsapp", color: [37,211,102]}, ...]
    keyword_rules: list = field(default_factory=list)


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    # Optional multi-device list (each item a DeviceConfig-shaped dict). When
    # empty, the single `device` + `capture.monitor_index` is used (back-compat).
    devices: list = field(default_factory=list)
    zones: ZoneConfig = field(default_factory=ZoneConfig)
    color: ColorConfig = field(default_factory=ColorConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    gradient: GradientConfig = field(default_factory=GradientConfig)
    effects: EffectsConfig = field(default_factory=EffectsConfig)
    auto_profile: AutoProfileConfig = field(default_factory=AutoProfileConfig)
    gpu: GpuConfig = field(default_factory=GpuConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


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
    import sys

    if not dataclasses.is_dataclass(cls):
        return data

    field_types = {f.name: f.type for f in dataclasses.fields(cls)}
    # `from __future__ import annotations` makes field types strings; resolve them
    # in the *defining module's* namespace, not the caller's frame (TD-11). This
    # makes nesting work for every caller (config update, profile import, tests).
    module_globals = getattr(sys.modules.get(cls.__module__), "__dict__", {})
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in field_types:
            logger.warning("Unknown config key '%s' in section '%s'; ignoring.", key, cls.__name__)
            continue
        type_hint = field_types[key]
        # Resolve string annotations (e.g. from __future__ annotations)
        if isinstance(type_hint, str):
            try:
                resolved = eval(type_hint, module_globals)  # noqa: S307
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
    _loaded_path: str = "configuration.yaml"

    @classmethod
    def loaded_path(cls) -> str:
        """Path the config was last loaded from (used by the file watcher)."""
        return cls._loaded_path

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

        cls._normalize_and_validate(config)

        cls._instance = config
        cls._loaded_path = str(path)
        return config

    # ------------------------------------------------------------------
    # Normalisation / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_index(value: Any, default: int, label: str) -> int:
        """Coerce a monitor index to a non-negative int, warning on bad input.

        Config drift (e.g. ``monitor_index: '2'`` as a YAML string, or a value
        pointing at a monitor that doesn't exist) silently breaks capture: the
        wrong monitor — or none — gets grabbed and the LEDs freeze. Coerce here
        and let the pipeline clamp against the real monitor count at start.
        """
        try:
            idx = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "[Config] %s=%r is not an integer; falling back to %d.",
                label, value, default,
            )
            return default
        if idx < 0:
            logger.warning("[Config] %s=%d is negative; using 0.", label, idx)
            return 0
        return idx

    @classmethod
    def _normalize_and_validate(cls, config: AppConfig) -> None:
        """Coerce types and surface obviously-broken values at load time.

        Doesn't mutate the user's intent — it fixes type drift (string indices),
        and *warns* about suspicious values (out-of-range LED counts, conflicting
        MACs) so misconfigurations are visible in the log instead of manifesting
        as "service active but lights static".
        """
        # 1. monitor_index must be a non-negative int on capture, device, and
        #    every multi-device entry.
        config.capture.monitor_index = cls._coerce_index(
            config.capture.monitor_index, 0, "capture.monitor_index"
        )
        config.device.monitor_index = cls._coerce_index(
            config.device.monitor_index, config.capture.monitor_index, "device.monitor_index"
        )
        for i, dev in enumerate(config.devices):
            if isinstance(dev, dict) and "monitor_index" in dev:
                dev["monitor_index"] = cls._coerce_index(
                    dev["monitor_index"], 0, f"devices[{i}].monitor_index"
                )

        # 1b. monitor_id is a free-form stable identity string; coerce to str so
        #     a YAML scalar (e.g. a bare number) can't break identity matching.
        config.capture.monitor_id = str(config.capture.monitor_id or "")
        config.device.monitor_id = str(config.device.monitor_id or "")
        for dev in config.devices:
            if isinstance(dev, dict) and dev.get("monitor_id") is not None:
                dev["monitor_id"] = str(dev.get("monitor_id") or "")

        # 2. led_count sanity — a single-RGB strip is one channel; even long
        #    addressable strips rarely exceed a few hundred LEDs. Absurd values
        #    (e.g. 3000) usually mean a stale/typo'd config.
        def _check_led_count(count: Any, label: str) -> int:
            try:
                n = int(count)
            except (TypeError, ValueError):
                logger.warning("[Config] %s=%r is not an integer; defaulting to 30.", label, count)
                return 30
            if n <= 0 or n > 1000:
                logger.warning(
                    "[Config] %s=%d looks wrong (expected 1–1000). Single-RGB "
                    "strips use 30; clamping to 30.", label, n,
                )
                return 30
            return n

        config.device.led_count = _check_led_count(config.device.led_count, "device.led_count")
        for i, dev in enumerate(config.devices):
            if isinstance(dev, dict) and "led_count" in dev:
                dev["led_count"] = _check_led_count(dev["led_count"], f"devices[{i}].led_count")

        # 3. MAC consistency — discovery keys off MAC to recover after an IP
        #    change, so conflicting MACs across device/devices defeat it. Warn
        #    (don't rewrite — we can't know which is correct).
        def _norm_mac(mac: Any) -> str:
            return str(mac or "").lower().replace("-", ":").strip()

        dev_mac = _norm_mac(config.device.mac)
        for i, dev in enumerate(config.devices):
            if not isinstance(dev, dict):
                continue
            entry_mac = _norm_mac(dev.get("mac"))
            same_ip = str(dev.get("ip", "")) == str(config.device.ip)
            if dev_mac and entry_mac and same_ip and dev_mac != entry_mac:
                logger.warning(
                    "[Config] MAC mismatch for %s: device.mac=%s vs devices[%d].mac=%s. "
                    "Discovery may target the wrong controller; reconcile them.",
                    config.device.ip, dev_mac, i, entry_mac,
                )

        # 4. protocol — normalise to lowercase; unknown values fall back to the
        #    historical default so a typo never breaks the pipeline.
        def _norm_protocol(proto: Any, label: str) -> str:
            p = str(proto or "magichome").strip().lower()
            if p not in _KNOWN_PROTOCOLS:
                logger.warning(
                    "[Config] %s=%r is not a known protocol %s; using 'magichome'.",
                    label, proto, sorted(_KNOWN_PROTOCOLS),
                )
                return "magichome"
            return p

        config.device.protocol = _norm_protocol(config.device.protocol, "device.protocol")
        for i, dev in enumerate(config.devices):
            if isinstance(dev, dict) and "protocol" in dev:
                dev["protocol"] = _norm_protocol(dev["protocol"], f"devices[{i}].protocol")

        # 5. MQTT — normalise topic, clamp port, and disable on a blank broker so
        #    an enabled-but-misconfigured bridge can't spin on a bad connection.
        mqtt = config.mqtt
        # Enforce the write-only password contract even for configs that didn't
        # come through the API (manual YAML edits / legacy files): migrate any
        # plaintext password into the OS keyring and scrub it so save() can't
        # round-trip it back to configuration.yaml.
        if str(mqtt.password or ""):
            try:
                from .integrations import secrets_store
                secrets_store.set_mqtt_password(str(mqtt.password))
            except Exception as exc:  # pragma: no cover - keyring/backend specific
                logger.warning("[Config] could not migrate mqtt.password to keyring: %s", exc)
            mqtt.password = ""
        mqtt.broker = str(mqtt.broker or "").strip()
        mqtt.base_topic = (mqtt.base_topic or "ambilight").strip().strip("/").lower() or "ambilight"
        try:
            mqtt.port = int(mqtt.port)
        except (TypeError, ValueError):
            mqtt.port = 1883
        if not 1 <= mqtt.port <= 65535:
            logger.warning("[Config] mqtt.port=%s out of range; using 1883.", mqtt.port)
            mqtt.port = 1883
        if mqtt.enabled and not mqtt.broker:
            logger.warning("[Config] mqtt.enabled but mqtt.broker is blank; disabling MQTT.")
            mqtt.enabled = False

        # 6. Notifications — clamp flash params and coerce colours to 3 ints 0..255
        #    so a malformed value never crashes the listener or sends garbage to
        #    the strip.
        def _norm_color(value: Any, default: list, label: str) -> list:
            try:
                rgb = [int(c) for c in value]
                if len(rgb) != 3:
                    raise ValueError
            except (TypeError, ValueError):
                logger.warning("[Config] %s=%r is not an [r,g,b] colour; using %r.", label, value, default)
                return list(default)
            return [max(0, min(255, c)) for c in rgb]

        n = config.notifications
        n.default_color = _norm_color(n.default_color, [255, 255, 255], "notifications.default_color")
        try:
            n.brightness = max(0.0, min(1.0, float(n.brightness)))
        except (TypeError, ValueError):
            n.brightness = 1.0
        try:
            n.blink_count = max(1, int(n.blink_count))
        except (TypeError, ValueError):
            n.blink_count = 2
        try:
            n.on_ms = max(20, int(n.on_ms))
        except (TypeError, ValueError):
            n.on_ms = 180
        try:
            n.off_ms = max(0, int(n.off_ms))
        except (TypeError, ValueError):
            n.off_ms = 120
        # Canonicalise to lowercase so runtime checks (which compare against
        # "fixed") match regardless of how the value was entered (e.g. "FIXED").
        n.color_mode = str(n.color_mode or "icon").strip().lower()
        if n.color_mode not in ("icon", "fixed"):
            logger.warning("[Config] notifications.color_mode=%r unknown; using 'icon'.", n.color_mode)
            n.color_mode = "icon"
        # Normalise keyword rules' colours so the resolver always gets clean RGB.
        # Guard the container type: a malformed truthy value (e.g. keyword_rules: 1)
        # must not raise during load.
        raw_rules = n.keyword_rules if isinstance(n.keyword_rules, list) else []
        if not isinstance(n.keyword_rules, list) and n.keyword_rules:
            logger.warning("[Config] notifications.keyword_rules is not a list; ignoring.")
        clean_rules = []
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            kw = str(rule.get("keyword", "")).strip()
            if not kw:
                continue
            clean_rules.append({
                "keyword": kw,
                "color": _norm_color(rule.get("color"), [255, 255, 255], "notifications.keyword_rules[].color"),
            })
        n.keyword_rules = clean_rules
        # Per-app override colours (guard the container type as above).
        raw_overrides = n.app_overrides if isinstance(n.app_overrides, dict) else {}
        if not isinstance(n.app_overrides, dict) and n.app_overrides:
            logger.warning("[Config] notifications.app_overrides is not a mapping; ignoring.")
        n.app_overrides = {
            str(k): _norm_color(v, [255, 255, 255], f"notifications.app_overrides[{k}]")
            for k, v in raw_overrides.items()
        }

    @classmethod
    def get(cls) -> AppConfig:
        """
        Return the loaded configuration, loading defaults if never called.
        """
        if cls._instance is None:
            cls._instance = AppConfig()
        return cls._instance

    @classmethod
    def save(cls, path: str | Path | None = None) -> bool:
        """Atomically save the current configuration.

        Defaults to the path the config was loaded from (``_loaded_path``) so
        UI/API edits persist back to the same file — critical for installed
        builds where the load path is the writable ``~/.ambilight/configuration.yaml``
        rather than a (read-only) bundled default.

        Returns *True* once the write reached disk, *False* otherwise — callers
        that mutate in-memory state to mark something "persisted" (e.g. the
        monitor_id backfill) must gate on this so a swallowed write failure
        doesn't suppress later retries.
        """
        if cls._instance is None:
            return False

        if path is None:
            path = cls._loaded_path
        path = Path(path)
        import dataclasses
        import tempfile
        import os

        try:
            # Write to a temporary file in the same directory, then replace atomically
            temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp", text=True)
            with os.fdopen(temp_fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(dataclasses.asdict(cls._instance), fh, default_flow_style=False, sort_keys=False)
            os.replace(temp_path, path)
            logger.debug("Configuration saved atomically to %s", path)
            return True
        except Exception as exc:
            logger.error("Failed to save configuration: %s", exc)
            return False

    @classmethod
    def update(cls, override: dict[str, Any], path: str | Path | None = None) -> None:
        """Merge a dictionary of overrides into the current configuration and save.

        ``path`` defaults to ``_loaded_path`` (see :meth:`save`).
        """
        if cls._instance is None:
            return

        import dataclasses
        base = dataclasses.asdict(cls._instance)
        merged = _merge(base, override)

        # Re-build the dataclass
        cls._instance = _dict_to_dataclass(AppConfig, merged)
        if not isinstance(cls._instance, AppConfig):
            cls._instance = AppConfig()

        # Apply the same clamping/normalization as load() so runtime/API edits
        # can't bypass it (MQTT port/broker/topic, notification colours, the
        # write-only password scrub, etc.).
        cls._normalize_and_validate(cls._instance)

        cls.save(path)

