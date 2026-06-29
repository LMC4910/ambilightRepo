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
    method: str = "wgc"           # wgc | dxgi | mss | hook
    monitor_index: int = 0        # 0 = primary (fallback when monitor_id is unset)
    monitor_id: str = ""          # stable monitor identity (EDID/gdi_name/pos); see monitors.py
    fps_target: int = 30
    analysis_width: int = 80
    analysis_height: int = 45
    hdr: HdrConfig = field(default_factory=HdrConfig)
    # Opt-in "hook" backend only (DX11 game capture via the native helper). Empty
    # = auto-detect the foreground fullscreen game; otherwise a target exe name
    # (e.g. "game.exe"). Unused by the other backends; reserved for Phase 2.
    hook_target: str = ""


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
class OwnershipConfig:
    """Cross-instance device exclusivity (cooperative ownership).

    When two Ambilight instances on the same LAN can both reach a controller,
    the hardware (MagicHome accepts any TCP client; WLED is stateless UDP) cannot
    arbitrate — so instances cooperatively claim devices and a deterministic rule
    decides who drives, preventing last-packet-wins flicker. A claim is keyed by
    device identity (MAC for magichome, IP for wled) and kept alive by a
    heartbeat; a crashed owner's claim expires after ``ttl`` and another instance
    takes over. Coordination uses MQTT when a broker is configured, else a LAN
    UDP announce. Off changes nothing for single-instance setups (you always win
    an unclaimed device).
    """
    enabled: bool = True
    instance_id: str = ""            # stable per-install UUID; auto-minted on first load
    instance_label: str = ""         # human label for the UI; blank → hostname
    priority: int = 0                # higher wins a contested device
    heartbeat_interval: float = 10.0  # seconds between claim re-announcements
    ttl: float = 30.0                # a claim older than this (no heartbeat) is stale
    lan_port: int = 48900            # UDP port for the LAN announce fallback


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
    min_flash_interval_s: float = 1.5  # DEPRECATED: bursts are now queued, not dropped (retained for back-compat)
    inter_flash_gap_ms: int = 120    # dark gap between consecutive queued flashes so they stay visually distinct
    flash_max_retries: int = 3       # retry a failed flash up to N times before moving on to the next
    # Per-app custom colours: {app_id_or_name: [r,g,b]}
    app_overrides: dict = field(default_factory=dict)
    # Keyword→colour rules (Phone Link / forwarded), ordered:
    #   [{keyword: "whatsapp", color: [37,211,102]}, ...]
    keyword_rules: list = field(default_factory=list)


# Bump when DEFAULT_GITHUB_RULES gains entries that existing installs should pick
# up. On load, configs with an older github.rules_version get the *missing*
# defaults merged in (by signature) without disturbing the user's custom rules —
# so upgrades top-up new defaults exactly once and never resurrect a default the
# user deliberately deleted.
DEFAULT_GITHUB_RULES_VERSION = 1

# Sensible starter colour rules, seeded once so the integration lights up out of
# the box (workflow → repo → org → global precedence; the user can edit/clear
# them in the Integrations → GitHub tab). A blank action matches any action.
DEFAULT_GITHUB_RULES = [
    # CI / GitHub Actions
    {"scope": "global", "event_type": "workflow_run", "action": "failure", "color": [220, 38, 38], "blink_count": 4},
    {"scope": "global", "event_type": "workflow_run", "action": "success", "color": [34, 197, 94]},
    {"scope": "global", "event_type": "workflow_run", "action": "cancelled", "color": [148, 163, 184]},
    {"scope": "global", "event_type": "workflow_run", "action": "in_progress", "color": [234, 179, 8]},
    {"scope": "global", "event_type": "workflow_job", "action": "in_progress", "color": [234, 179, 8]},
    {"scope": "global", "event_type": "workflow_job", "action": "completed", "color": [148, 163, 184]},
    {"scope": "global", "event_type": "check_run", "action": "created", "color": [56, 189, 248]},
    {"scope": "global", "event_type": "check_run", "action": "completed", "color": [148, 163, 184]},
    # Pull requests
    {"scope": "global", "event_type": "pull_request", "action": "opened", "color": [59, 130, 246]},
    {"scope": "global", "event_type": "pull_request", "action": "merged", "color": [168, 85, 247]},
    {"scope": "global", "event_type": "pull_request", "action": "closed", "color": [148, 163, 184]},
    {"scope": "global", "event_type": "pull_request", "action": "review_requested", "color": [192, 132, 252]},
    {"scope": "global", "event_type": "pull_request_review", "action": "", "color": [192, 132, 252]},
    {"scope": "global", "event_type": "review_comment", "action": "", "color": [129, 140, 248]},
    # Issues
    {"scope": "global", "event_type": "issue", "action": "opened", "color": [6, 182, 212]},
    {"scope": "global", "event_type": "issue", "action": "assigned", "color": [14, 165, 233]},
    {"scope": "global", "event_type": "issue", "action": "closed", "color": [22, 101, 52]},
    {"scope": "global", "event_type": "issue_comment", "action": "", "color": [56, 189, 248]},
    # Mentions / review-requests / assignments (any event type)
    {"scope": "global", "event_type": "", "action": "mentioned", "color": [249, 115, 22], "blink_count": 3},
    {"scope": "global", "event_type": "", "action": "review_requested", "color": [192, 132, 252]},
    {"scope": "global", "event_type": "", "action": "assigned", "color": [14, 165, 233]},
    # Releases / packages
    {"scope": "global", "event_type": "release", "action": "", "color": [250, 204, 21]},
    # Repo activity
    {"scope": "global", "event_type": "push", "action": "", "color": [100, 116, 139]},
    {"scope": "global", "event_type": "branch", "action": "created", "color": [52, 211, 153]},
    {"scope": "global", "event_type": "branch", "action": "deleted", "color": [148, 163, 184]},
    {"scope": "global", "event_type": "star", "action": "", "color": [250, 204, 21]},
    {"scope": "global", "event_type": "fork", "action": "", "color": [125, 211, 252]},
    {"scope": "global", "event_type": "discussion", "action": "", "color": [45, 212, 191]},
    {"scope": "global", "event_type": "discussion_comment", "action": "", "color": [20, 184, 166]},
    {"scope": "global", "event_type": "commit_comment", "action": "", "color": [14, 165, 233]},
    {"scope": "global", "event_type": "deployment", "action": "", "color": [99, 102, 241]},
    {"scope": "global", "event_type": "deployment_status", "action": "", "color": [79, 70, 229]},
    {"scope": "global", "event_type": "repository_invitation", "action": "", "color": [251, 191, 36], "blink_count": 3},
    # Security — urgent flashing red
    {"scope": "global", "event_type": "security_alert", "action": "", "color": [239, 68, 68], "blink_count": 6, "on_ms": 120, "off_ms": 80},
]


@dataclass
class GithubConfig:
    """"Ambient GitHub Awareness" — flash the LEDs in response to GitHub activity.

    The integration polls GitHub (works behind NAT) and maps each event to a
    colour/effect using a rule hierarchy (workflow → repo → org → global). All
    colours are user-defined here — there is no brand-colour lookup. Off by
    default; a no-op without the optional ``httpx`` dependency. The OAuth token
    is stored in the OS keyring, never in this config.
    """
    enabled: bool = False
    # OAuth App client id for the device flow (public; no secret). May be left
    # blank and supplied via the AMBILIGHT_GITHUB_CLIENT_ID env var instead.
    client_id: str = ""
    scopes: list = field(default_factory=lambda: ["notifications", "read:org", "repo"])
    # Polling
    poll_interval_s: float = 60.0        # base interval; clamped, honours X-Poll-Interval
    watch_notifications: bool = True     # poll the /notifications inbox
    watched_repos: list = field(default_factory=list)  # ["owner/name", ...] for runs + events
    watched_orgs: list = field(default_factory=list)    # ["org", ...] for org events
    # Default lighting (fallback when no rule matches) — GitHub blue.
    default_color: list = field(default_factory=lambda: [88, 166, 255])  # [r,g,b]
    brightness: float = 1.0
    blink_count: int = 2
    on_ms: int = 180
    off_ms: int = 120
    # Rule hierarchy (see integrations/github/mapper.py). Each rule is a dict:
    #   {scope, repo?, org?, workflow?, event_type, action, color:[r,g,b], <pattern overrides>}
    rules: list = field(default_factory=list)
    # Marker that defaults were seeded at least once. Kept for back-compat and
    # diagnostics; defaults still auto-reseed when rules are empty.
    rules_seeded: bool = False
    # Highest DEFAULT_GITHUB_RULES_VERSION whose defaults have been merged into
    # `rules`. Lets an upgrade top-up newly-added defaults once (see config load).
    rules_version: int = 0
    # Advanced: inbound webhook receiver (optional, off by default). When on, the
    # app opens a tunnel to make its loopback receiver reachable and auto-registers
    # a hook on each watched repo it admins; polling for those repos is then
    # skipped (the notifications inbox + non-admin repos keep polling). See
    # integrations/github/tunnel.py and service.enable_webhooks().
    webhook_enabled: bool = False
    webhook_secret_set: bool = False     # marker only; the secret lives in the keyring
    webhook_provider: str = "cloudflared"  # tunnel provider (only cloudflared today)
    # Optional stable "named tunnel" (Cloudflare account + domain) instead of an
    # ephemeral trycloudflare URL. The tunnel token lives in the keyring.
    tunnel_named: bool = False
    tunnel_hostname: str = ""            # e.g. "ambilight.example.com" for a named tunnel


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
    ownership: OwnershipConfig = field(default_factory=OwnershipConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    github: GithubConfig = field(default_factory=GithubConfig)


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

        # Remember whether the ownership instance_id was already present so we can
        # persist a freshly-minted one (normalize fills it in-memory below).
        id_before = str(getattr(config.ownership, "instance_id", "") or "").strip()

        cls._normalize_and_validate(config)

        cls._instance = config
        cls._loaded_path = str(path)
        # Persist a newly-minted instance_id so the install's identity is stable
        # across restarts (required for sticky ownership claims).
        if not id_before and config.ownership.instance_id:
            cls.save()
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
        try:
            n.inter_flash_gap_ms = max(0, int(n.inter_flash_gap_ms))
        except (TypeError, ValueError):
            n.inter_flash_gap_ms = 120
        try:
            n.flash_max_retries = max(1, int(n.flash_max_retries))
        except (TypeError, ValueError):
            n.flash_max_retries = 3
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

        # 6b. GitHub integration — clamp flash params, coerce colours, and
        #     sanitise the watch lists / rules so a malformed value can't crash
        #     the poller or send garbage to the strip.
        g = config.github
        g.enabled = bool(g.enabled)
        g.client_id = str(g.client_id or "").strip()
        g.scopes = [str(s).strip() for s in (g.scopes if isinstance(g.scopes, list) else []) if str(s).strip()] \
            or ["notifications", "read:org", "repo"]
        try:
            g.poll_interval_s = max(15.0, float(g.poll_interval_s))
        except (TypeError, ValueError):
            g.poll_interval_s = 60.0
        g.watch_notifications = bool(g.watch_notifications)
        g.watched_repos = [str(r).strip() for r in (g.watched_repos if isinstance(g.watched_repos, list) else []) if str(r).strip()]
        g.watched_orgs = [str(o).strip() for o in (g.watched_orgs if isinstance(g.watched_orgs, list) else []) if str(o).strip()]
        g.default_color = _norm_color(g.default_color, [88, 166, 255], "github.default_color")
        try:
            g.brightness = max(0.0, min(1.0, float(g.brightness)))
        except (TypeError, ValueError):
            g.brightness = 1.0
        try:
            g.blink_count = max(1, int(g.blink_count))
        except (TypeError, ValueError):
            g.blink_count = 2
        try:
            g.on_ms = max(20, int(g.on_ms))
        except (TypeError, ValueError):
            g.on_ms = 180
        try:
            g.off_ms = max(0, int(g.off_ms))
        except (TypeError, ValueError):
            g.off_ms = 120

        try:
            g.rules_version = max(0, int(g.rules_version))
        except (TypeError, ValueError):
            g.rules_version = 0

        # Seed/refresh the default colour rules so the integration lights up out
        # of the box. Three cases:
        #   * no rules at all → seed the full default set (also self-heals if a
        #     user clears every rule accidentally);
        #   * older rules_version → additively merge in any default the user is
        #     missing (matched by signature) without touching their custom rules,
        #     so an upgrade tops-up new defaults exactly once;
        #   * up-to-date → leave rules as-is.
        # The mapper's precedence (workflow > repo > org > global) means the
        # merged global defaults never override a user's more-specific rule.
        existing_rules = g.rules if isinstance(g.rules, list) else []

        def _rule_sig(r):
            return (
                str(r.get("scope", "global") or "global").strip().lower(),
                str(r.get("event_type", "") or "").strip().lower(),
                str(r.get("action", "") or "").strip().lower(),
                str(r.get("repo", "") or "").strip().lower(),
                str(r.get("org", "") or "").strip().lower(),
                str(r.get("workflow", "") or "").strip().lower(),
            )

        if not existing_rules:
            g.rules = [dict(r) for r in DEFAULT_GITHUB_RULES]
        elif g.rules_seeded and g.rules_version < DEFAULT_GITHUB_RULES_VERSION:
            # Existing install (already seeded once) on an older defaults version:
            # top-up the defaults it's missing. Gating on rules_seeded means a
            # pristine config that set rules explicitly is left untouched.
            seen = {_rule_sig(r) for r in existing_rules if isinstance(r, dict)}
            merged = list(existing_rules)
            for r in DEFAULT_GITHUB_RULES:
                if _rule_sig(r) not in seen:
                    merged.append(dict(r))
                    seen.add(_rule_sig(r))
            g.rules = merged
        g.rules_seeded = True
        g.rules_version = DEFAULT_GITHUB_RULES_VERSION

        raw_gh_rules = g.rules if isinstance(g.rules, list) else []
        if not isinstance(g.rules, list) and g.rules:
            logger.warning("[Config] github.rules is not a list; ignoring.")
        clean_gh_rules = []
        for rule in raw_gh_rules:
            if not isinstance(rule, dict):
                continue
            scope = str(rule.get("scope", "global") or "global").strip().lower()
            if scope not in ("global", "org", "repo", "workflow"):
                scope = "global"
            cleaned = {
                "scope": scope,
                "repo": str(rule.get("repo", "") or "").strip(),
                "org": str(rule.get("org", "") or "").strip(),
                "workflow": str(rule.get("workflow", "") or "").strip(),
                "event_type": str(rule.get("event_type", "") or "").strip(),
                "action": str(rule.get("action", "") or "").strip(),
                "color": _norm_color(rule.get("color"), g.default_color, "github.rules[].color"),
            }
            # Optional per-rule pattern overrides (kept only when present + valid).
            for k, lo in (("blink_count", 1), ("on_ms", 20), ("off_ms", 0)):
                if rule.get(k) is not None:
                    try:
                        cleaned[k] = max(lo, int(rule[k]))
                    except (TypeError, ValueError):
                        pass
            if rule.get("brightness") is not None:
                try:
                    cleaned["brightness"] = max(0.0, min(1.0, float(rule["brightness"])))
                except (TypeError, ValueError):
                    pass
            clean_gh_rules.append(cleaned)
        g.rules = clean_gh_rules
        g.webhook_enabled = bool(g.webhook_enabled)
        g.webhook_secret_set = bool(g.webhook_secret_set)
        g.webhook_provider = str(g.webhook_provider or "cloudflared").strip().lower() or "cloudflared"
        g.tunnel_named = bool(g.tunnel_named)
        g.tunnel_hostname = str(g.tunnel_hostname or "").strip()

        # 7. Ownership — mint a stable per-install instance_id (persisted by
        #    load()/update() so it survives restarts), default the label to the
        #    hostname (mirrors mqtt.device_id), and clamp the timing knobs so a
        #    bad value can't make heartbeats spin or claims never expire.
        import socket
        import uuid

        o = config.ownership
        if not str(o.instance_id or "").strip():
            o.instance_id = uuid.uuid4().hex
        else:
            o.instance_id = str(o.instance_id).strip()
        if not str(o.instance_label or "").strip():
            try:
                o.instance_label = socket.gethostname() or o.instance_id[:8]
            except Exception:
                o.instance_label = o.instance_id[:8]
        try:
            o.priority = int(o.priority)
        except (TypeError, ValueError):
            o.priority = 0
        try:
            o.heartbeat_interval = max(1.0, float(o.heartbeat_interval))
        except (TypeError, ValueError):
            o.heartbeat_interval = 10.0
        try:
            # ttl must exceed the heartbeat or a live owner's claim would expire
            # between beats; floor it at 2× the interval.
            o.ttl = max(float(o.ttl), 2.0 * o.heartbeat_interval)
        except (TypeError, ValueError):
            o.ttl = max(30.0, 2.0 * o.heartbeat_interval)
        try:
            o.lan_port = int(o.lan_port)
        except (TypeError, ValueError):
            o.lan_port = 48900
        if not 1 <= o.lan_port <= 65535:
            logger.warning("[Config] ownership.lan_port=%s out of range; using 48900.", o.lan_port)
            o.lan_port = 48900

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

