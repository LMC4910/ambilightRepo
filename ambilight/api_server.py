"""
API Server Module
=================
Exposes a FastAPI REST interface and WebSocket for real-time telemetry.
Provides control over the PipelineController.
"""

import asyncio
import logging
import time
import os
import json
import platform
import dataclasses
from collections import deque
from typing import Any, Dict, List, Optional

import pydantic
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.middleware.cors import CORSMiddleware

from . import __version__ as APP_VERSION
from .config import ConfigManager
from .events import bus
from .platform_monitor import get_platform_monitor
from .pipeline_controller import PipelineController
from .auth import generate_and_save_token, verify_token
from . import auth
from .profile_manager import profile_manager
from .discovery import (
    DeviceScanner, DeviceCache, DeviceInfo, CapabilityProbe, classify_device,
    full_scan, _wled_probe,
)
from .led_output import MagicHomeController
from .devices import create_driver
from .config_watcher import ConfigWatcher
from .auto_profile import AutoProfileSwitcher
from .foreground import get_foreground_app
from .integrations.mqtt_bridge import MqttBridge
from .notifications import NotificationFlashService
from .ownership import OwnershipCoordinator

logger = logging.getLogger(__name__)

app = FastAPI(title="Ambilight Desktop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local UI will bind to this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Globals
controller = PipelineController()
monitor = None
config_watcher = None
auto_switcher = None
mqtt_bridge = None
notification_flash = None
coordinator = None

# Most recent metrics snapshot (for /health). Updated on every METRICS_UPDATE.
latest_metrics: Dict[str, Any] = {}
service_start_time = time.monotonic()

# Rolling diagnostics window (~60 s at ~30 fps) persisted to disk for the UI.
AMBILIGHT_DIR = os.path.join(os.path.expanduser("~"), ".ambilight")
METRICS_FILE = os.path.join(AMBILIGHT_DIR, "metrics", "latest.json")
metrics_history: "deque[Dict[str, Any]]" = deque(maxlen=1800)
_last_metrics_persist = 0.0

@app.on_event("startup")
async def startup_event() -> None:
    global monitor, config_watcher, auto_switcher, mqtt_bridge, notification_flash, coordinator

    # 0. Security: Generate Token
    generate_and_save_token()

    logger.info("[API] Starting up. Initializing Pipeline Controller & Platform Monitor.")

    # 1. Start Platform Monitor to watch for sleep/lock events
    monitor = get_platform_monitor(asyncio.get_running_loop())
    monitor.start()

    # 1b. Watch configuration.yaml for on-disk edits → hot-reload (FR-SVC-06)
    config_watcher = ConfigWatcher(ConfigManager.loaded_path(), asyncio.get_running_loop())
    config_watcher.start()

    # 2. Setup Pipeline Controller (subscribes to events)
    await controller.setup()

    # 2b. Cross-instance ownership coordinator: claims devices on the LAN (over
    #     MQTT when a broker is set, else UDP) and publishes OWNERSHIP_UPDATE so
    #     the pipeline only drives strips this instance owns — preventing two
    #     instances on the same network from fighting over a controller. Created
    #     before the capture process so it can gate output from boot.
    coordinator = OwnershipCoordinator(ConfigManager.get())

    async def _refresh_ownership(cfg) -> None:
        if coordinator is not None:
            coordinator.update_config(cfg)

    await bus.subscribe("CONFIG_UPDATE", _refresh_ownership)
    coordinator.start()

    # 3. Start the actual capture process
    controller.start()

    # 4. Subscribe the WebSocket manager + metrics cache to METRICS_UPDATE
    await bus.subscribe("METRICS_UPDATE", push_metrics_to_ws)
    await bus.subscribe("METRICS_UPDATE", _cache_metrics)

    # 5. Auto-profile switcher: apply a profile based on the foreground app
    #    (FR-PROF-07). Refresh its rules whenever the config changes.
    auto_switcher = AutoProfileSwitcher(ConfigManager.get())

    async def _refresh_auto_profile(cfg) -> None:
        if auto_switcher is not None:
            auto_switcher.update_config(cfg)

    await bus.subscribe("CONFIG_UPDATE", _refresh_auto_profile)
    auto_switcher.start()

    # 6. MQTT bridge + Home Assistant discovery (off by default; no-op without
    #    paho-mqtt). Mirrors the auto-switcher lifecycle: refresh on config
    #    change, publish state on every metrics update.
    mqtt_bridge = MqttBridge(ConfigManager.get(), controller)

    async def _refresh_mqtt(cfg) -> None:
        if mqtt_bridge is not None:
            mqtt_bridge.update_config(cfg)

    await bus.subscribe("CONFIG_UPDATE", _refresh_mqtt)
    await bus.subscribe("METRICS_UPDATE", mqtt_bridge.on_metrics)
    mqtt_bridge.start()

    # 7. Notification Flash: blink the strip when an OS notification arrives so
    #    the user notices it in fullscreen / DND / locked. Mirrors the
    #    auto-switcher lifecycle (refresh rules on config change).
    notification_flash = NotificationFlashService(
        ConfigManager.get(), controller, asyncio.get_running_loop(),
    )

    async def _refresh_notifications(cfg) -> None:
        if notification_flash is not None:
            notification_flash.update_config(cfg)

    await bus.subscribe("CONFIG_UPDATE", _refresh_notifications)
    notification_flash.start()


async def _cache_metrics(metrics: dict) -> None:
    """Keep the latest snapshot + a rolling window; persist to disk ~1 Hz."""
    global latest_metrics, _last_metrics_persist
    latest_metrics = metrics
    metrics_history.append({
        "t": time.time(),
        "fps": metrics.get("fps", 0.0),
        "latency_ms": metrics.get("latency_ms", 0.0),
    })
    now = time.monotonic()
    if now - _last_metrics_persist >= 1.0:
        _last_metrics_persist = now
        try:
            os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
            tmp = METRICS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(list(metrics_history), fh)
            os.replace(tmp, METRICS_FILE)
        except Exception as exc:
            logger.debug("[API] metrics persist failed: %s", exc)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("[API] Shutting down. Stopping pipeline.")
    controller.stop()
    if coordinator:
        coordinator.stop()
    if mqtt_bridge:
        mqtt_bridge.stop()
    if notification_flash:
        notification_flash.stop()
    if monitor:
        monitor.stop()
    if config_watcher:
        config_watcher.stop()


# ---------------------------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------------------------

def _health_assessment() -> Dict[str, Any]:
    """Decide whether the service is actually *doing its job*, not just alive.

    The process being alive (``controller.status()["running"]``) is necessary
    but not sufficient — the LEDs can be frozen while the pipeline is up, e.g.
    capture is producing no frames (fullscreen game on the MSS backend, bad
    monitor_index, DRM) or the controller is unreachable. We fold those signals,
    published each frame in ``latest_metrics``, into the status so the UI can say
    "running but not syncing" instead of a flat green "active".

    Intentional non-syncing states (powered off, paused for sleep/lock) are NOT
    degraded.
    """
    st = controller.status()
    m = latest_metrics or {}
    running = bool(st["running"])
    paused = bool(st["paused"])
    power = bool(m.get("power", True))
    mode = m.get("mode", "")
    connected = int(m.get("devices_connected", 0))
    capture_ok = bool(m.get("capture_ok", True))
    # Why capture isn't usable (ok|no_frames|black|drm_suspected) and whether the
    # active backend is itself degraded (MSS on Windows — fullscreen games go
    # black). Both come from the pipeline's per-frame metrics.
    capture_reason = str(m.get("capture_reason", "ok"))
    capture_degraded = bool(m.get("degraded", False))

    reasons: list[str] = []
    if not running:
        reasons.append("pipeline_not_running")
    elif power and not paused:
        # Actively supposed to be driving the strip right now.
        if connected == 0:
            reasons.append("no_device_connected")
        if mode == "screen_sync" and not capture_ok:
            # "capture_unavailable" kept for back-compat; capture_reason carries
            # the specific cause (no_frames / black / drm_suspected) for the UI.
            reasons.append("capture_unavailable")

    status = "ok" if not reasons else "degraded"
    return {
        "status": status,
        "version": APP_VERSION,
        "pipeline_alive": running,
        "paused": paused,
        "restarts": st["restarts"],
        "fps": round(m.get("fps", 0.0), 1),
        "latency_ms": round(m.get("latency_ms", 0.0), 1),
        "uptime_s": round(time.monotonic() - service_start_time, 1),
        "devices_connected": connected,
        "capture_ok": capture_ok,
        "capture_backend": m.get("capture_backend"),
        "capture_reason": capture_reason,
        "capture_degraded": capture_degraded,
        "hdr_active": bool(m.get("hdr_active", False)),
        "degraded_reasons": reasons,
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Unauthenticated structured health probe (FR-SVC-08).

    Intentionally token-free so watchdogs / the Electron supervisor can poll it
    cheaply. It exposes no sensitive data — only liveness and coarse metrics.
    """
    return _health_assessment()


@app.get("/api/status", dependencies=[Depends(verify_token)])
async def get_status() -> Dict[str, Any]:
    st = controller.status()
    health = _health_assessment()
    return {
        "status": "running" if st["running"] else "stopped",
        "version": APP_VERSION,
        # Whether the strip is actually being driven right now (vs. just alive).
        "syncing": health["status"] == "ok" and st["running"] and not st["paused"],
        "health": health["status"],
        "degraded_reasons": health["degraded_reasons"],
        "devices_connected": health["devices_connected"],
        "capture_ok": health["capture_ok"],
        "capture_backend": health["capture_backend"],
        "capture_reason": health["capture_reason"],
        "capture_degraded": health["capture_degraded"],
        "hdr_active": health["hdr_active"],
        "paused": st["paused"],
        "pid": st["pid"],
        "restarts": st["restarts"],
        "active_profile": getattr(profile_manager, "active_profile", None),
    }


@app.post("/api/pipeline/start", dependencies=[Depends(verify_token)])
async def start_pipeline() -> Dict[str, str]:
    controller.start()
    return {"message": "Pipeline started"}


@app.post("/api/pipeline/stop", dependencies=[Depends(verify_token)])
async def stop_pipeline() -> Dict[str, str]:
    controller.stop()
    return {"message": "Pipeline stopped"}


@app.post("/api/pipeline/pause", dependencies=[Depends(verify_token)])
async def pause_pipeline() -> Dict[str, str]:
    controller.pause()
    return {"message": "Pipeline paused"}


@app.post("/api/pipeline/resume", dependencies=[Depends(verify_token)])
async def resume_pipeline() -> Dict[str, str]:
    controller.resume()
    return {"message": "Pipeline resumed"}


@app.post("/api/service/restart", dependencies=[Depends(verify_token)])
async def restart_service() -> Dict[str, str]:
    controller.restart()
    return {"message": "Pipeline restarted"}


@app.get("/api/config", dependencies=[Depends(verify_token)])
async def get_config() -> Dict[str, Any]:
    cfg = ConfigManager.get()
    return dataclasses.asdict(cfg)


@app.put("/api/config", dependencies=[Depends(verify_token)])
async def update_config(override: Dict[str, Any]) -> Dict[str, str]:
    # Move any incoming MQTT broker password to the OS keyring and blank it in
    # the override so the secret is never persisted to configuration.yaml. An
    # empty/absent password leaves the stored one untouched.
    mqtt_override = override.get("mqtt")
    if isinstance(mqtt_override, dict) and "password" in mqtt_override:
        pw = mqtt_override.get("password") or ""
        if pw:
            from .integrations import secrets_store
            secrets_store.set_mqtt_password(pw)
        mqtt_override["password"] = ""

    ConfigManager.update(override)
    # A manual settings edit no longer matches a saved profile (unless it *is*
    # the auto_profile rules being toggled).
    if set(override.keys()) - {"auto_profile"}:
        profile_manager.active_profile = None
    cfg = ConfigManager.get()
    await bus.publish("CONFIG_UPDATE", cfg)
    return {"message": "Config updated"}


@app.get("/api/profiles", dependencies=[Depends(verify_token)])
async def list_profiles() -> Dict[str, Any]:
    return {"profiles": profile_manager.list_profiles(), "active": profile_manager.active_profile}


@app.get("/api/profiles/{name}", dependencies=[Depends(verify_token)])
async def get_profile(name: str) -> Dict[str, Any]:
    prof = profile_manager.get_profile(name)
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return prof


@app.post("/api/profiles/{name}", dependencies=[Depends(verify_token)])
async def save_profile(name: str) -> Dict[str, str]:
    if profile_manager.save_profile(name):
        return {"message": f"Profile '{name}' saved"}
    raise HTTPException(status_code=500, detail="Failed to save profile")


@app.delete("/api/profiles/{name}", dependencies=[Depends(verify_token)])
async def delete_profile(name: str) -> Dict[str, str]:
    if profile_manager.delete_profile(name):
        return {"message": f"Profile '{name}' deleted"}
    raise HTTPException(status_code=404, detail="Profile not found or failed to delete")


@app.post("/api/profiles/{name}/import", dependencies=[Depends(verify_token)])
async def import_profile(name: str, data: Dict[str, Any]) -> Dict[str, str]:
    """Write an imported profile JSON body to disk under *name* (FR-PROF-05)."""
    if profile_manager.write_profile(name, data):
        return {"message": f"Profile '{name}' imported"}
    raise HTTPException(status_code=400, detail="Invalid profile data")


@app.post("/api/profiles/{name}/apply", dependencies=[Depends(verify_token)])
async def apply_profile(name: str) -> Dict[str, str]:
    if profile_manager.apply_profile(name):
        cfg = ConfigManager.get()
        await bus.publish("CONFIG_UPDATE", cfg)
        return {"message": f"Profile '{name}' applied"}
    raise HTTPException(status_code=404, detail="Profile not found or failed to apply")

class ModeRequest(pydantic.BaseModel):
    mode: str
    params: Dict[str, Any] = {}


class RetargetRequest(pydantic.BaseModel):
    # Game-capture re-inject. `target` is a game exe filter ("" / "auto" = any
    # fullscreen game). `enabled` switches capture.method to "hook".
    target: str = ""
    enabled: bool = True


@app.post("/api/capture/retarget", dependencies=[Depends(verify_token)])
async def capture_retarget(req: RetargetRequest) -> Dict[str, str]:
    """Point game capture at a specific application and (re)trigger injection.

    Persists capture.method=hook + capture.hook_target, then forces a fresh
    capture build so the native host relaunches and retries injection now."""
    capture_override: Dict[str, Any] = {"hook_target": req.target.strip()}
    if req.enabled:
        capture_override["method"] = "hook"
    ConfigManager.update({"capture": capture_override})
    profile_manager.active_profile = None
    cfg = ConfigManager.get()
    await bus.publish("CONFIG_UPDATE", cfg)
    controller.recapture()
    return {"message": "Re-targeting game capture", "target": req.target.strip() or "auto"}

@app.put("/api/mode", dependencies=[Depends(verify_token)])
async def set_mode(request: ModeRequest) -> Dict[str, str]:
    controller.set_mode(request.mode, request.params)
    return {"message": f"Mode set to {request.mode}"}


@app.get("/api/effects", dependencies=[Depends(verify_token)])
async def list_effects() -> Dict[str, List[str]]:
    """List selectable effect modes (built-ins + discovered plugins)."""
    import os
    from .effects_engine import EffectsManager
    mgr = EffectsManager()
    cfg = ConfigManager.get()
    eff = getattr(cfg, "effects", None)
    plugins_dir = (eff.plugins_dir if eff and eff.plugins_dir
                   else os.path.join(os.path.expanduser("~"), ".ambilight", "plugins"))
    try:
        mgr.load_plugins(plugins_dir)
    except Exception:
        pass
    return {"effects": mgr.list_effects()}


# ---------------------------------------------------------------------------
# DIAGNOSTICS & LOGS
# ---------------------------------------------------------------------------

@app.get("/api/diagnostics", dependencies=[Depends(verify_token)])
async def diagnostics() -> Dict[str, Any]:
    """System + runtime diagnostics for the UI Diagnostics page (FR-UI-12)."""
    cfg = ConfigManager.get()
    from .monitors import list_monitors
    monitors = await asyncio.get_running_loop().run_in_executor(None, list_monitors)
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "gpu": {"enabled": cfg.gpu.enabled, "prefer": cfg.gpu.prefer},
        "capture_method": cfg.capture.method,
        "monitors": monitors,
        "device": {"ip": cfg.device.ip, "mac": cfg.device.mac, "led_count": cfg.device.led_count},
        "pipeline": controller.status(),
        "metrics": latest_metrics,
        "history_points": len(metrics_history),
        "history": list(metrics_history)[-120:],
    }


@app.get("/api/logs", dependencies=[Depends(verify_token)])
async def get_logs(level: str = "", limit: int = 400) -> Dict[str, Any]:
    """Tail the rotating log file, optionally filtered by level substring."""
    cfg = ConfigManager.get()
    path = cfg.logging.file
    if not os.path.isabs(path):
        path = os.path.join(AMBILIGHT_DIR, path)
    lines: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-2000:]
    except FileNotFoundError:
        return {"lines": [], "file": path}
    if level:
        lvl = level.upper()
        lines = [ln for ln in lines if lvl in ln]
    return {"lines": [ln.rstrip("\n") for ln in lines[-limit:]], "file": path}


# ---------------------------------------------------------------------------
# FOREGROUND APP (for the auto-profile rules UI)
# ---------------------------------------------------------------------------

@app.get("/api/foreground", dependencies=[Depends(verify_token)])
async def foreground_app() -> Dict[str, Optional[str]]:
    app_name = await asyncio.get_running_loop().run_in_executor(None, get_foreground_app)
    return {"app": app_name}


# ---------------------------------------------------------------------------
# NOTIFICATION FLASH
# ---------------------------------------------------------------------------

@app.get("/api/notifications/permission", dependencies=[Depends(verify_token)])
async def notifications_permission() -> Dict[str, Any]:
    """Report whether notification access is granted, so the UI can deep-link to
    the relevant OS settings page when it isn't."""
    info = {"status": "unavailable", "available": False}
    if notification_flash is not None:
        info = await asyncio.get_running_loop().run_in_executor(
            None, notification_flash.permission_status,
        )
    info["platform"] = platform.system().lower()
    return info


class NotificationTestRequest(pydantic.BaseModel):
    color: Optional[List[int]] = None   # [r,g,b]; defaults to configured default


@app.post("/api/notifications/test", dependencies=[Depends(verify_token)])
async def notifications_test(request: NotificationTestRequest) -> Dict[str, str]:
    """Fire a flash now (bypassing dedup/DND) so the user can preview it."""
    if notification_flash is None:
        raise HTTPException(status_code=503, detail="Notification service not ready")
    color = request.color
    # Reject a malformed colour up front rather than reporting success for a
    # flash the pipeline would silently drop.
    if color is not None and (
        len(color) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in color)
    ):
        raise HTTPException(status_code=400, detail="color must be [r, g, b] with values 0-255")
    notification_flash.test_flash(color)
    return {"message": "Flash triggered"}


# ---------------------------------------------------------------------------
# AUTO-START (start on login)
# ---------------------------------------------------------------------------

@app.get("/api/autostart", dependencies=[Depends(verify_token)])
async def autostart_status() -> Dict[str, bool]:
    from . import autostart
    return {"enabled": autostart.status()}


@app.post("/api/autostart/enable", dependencies=[Depends(verify_token)])
async def autostart_enable() -> Dict[str, bool]:
    from . import autostart
    await asyncio.get_running_loop().run_in_executor(None, autostart.install)
    return {"enabled": autostart.status()}


@app.post("/api/autostart/disable", dependencies=[Depends(verify_token)])
async def autostart_disable() -> Dict[str, bool]:
    from . import autostart
    await asyncio.get_running_loop().run_in_executor(None, autostart.remove)
    return {"enabled": autostart.status()}


# ---------------------------------------------------------------------------
# DEVICE ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/api/devices", dependencies=[Depends(verify_token)])
async def list_devices() -> Dict[str, List[Dict[str, Any]]]:
    """Return the last-known devices from the on-disk cache (fast, no scan).

    Each record is annotated with its cross-instance ``device_key`` and current
    ``owner`` ({instance_id, label, is_self} or null when unclaimed) so the UI can
    show whether this instance or another one is driving the strip.
    """
    from .pipeline import device_key
    cfg = ConfigManager.get()
    cache = DeviceCache(path=cfg.device.cache_file)
    devices = await asyncio.get_running_loop().run_in_executor(None, cache.load)
    out: List[Dict[str, Any]] = []
    for d in devices:
        rec = d.to_dict()
        try:
            key = device_key({
                "protocol": rec.get("protocol", "magichome"),
                "mac": rec.get("mac", ""), "ip": rec.get("ip", ""),
            })
            rec["device_key"] = key
            rec["owner"] = coordinator.owner_of(key) if coordinator is not None else None
        except Exception:  # pragma: no cover - defensive
            rec["device_key"] = ""
            rec["owner"] = None
        out.append(rec)
    return {"devices": out}


@app.post("/api/devices/scan", dependencies=[Depends(verify_token)])
async def scan_devices() -> Dict[str, List[Dict[str, Any]]]:
    """Run a live device discovery (UDP broadcast + TCP scan fallback) and refresh the cache."""
    cfg = ConfigManager.get()
    loop = asyncio.get_running_loop()
    devices = await loop.run_in_executor(
        None, full_scan, cfg.device.subnet, cfg.device.discovery_timeout,
    )
    if devices:
        await loop.run_in_executor(None, DeviceCache(path=cfg.device.cache_file).save, devices)
    return {"devices": [d.to_dict() for d in devices]}


class DeviceTestRequest(pydantic.BaseModel):
    ip: str
    port: Optional[int] = None
    protocol: Optional[str] = None   # magichome (default) | wled


def _flash_device(ip: str, port: int, protocol: str = "magichome") -> bool:
    """Blocking helper: flash a controller white three times, then restore off.

    Protocol-agnostic — builds the driver via the factory and uses only the
    uniform LedDriver interface, so MagicHome and WLED both flash identically.
    """
    drv = create_driver({"protocol": protocol, "ip": ip, "port": port})
    if not drv.connect():
        return False
    was_on = drv.query_power()   # remember prior state so we can restore it
    try:
        if not drv.ensure_on():
            return False
        for _ in range(3):
            if not drv.set_rgb(255, 255, 255):
                return False
            time.sleep(0.25)
            if not drv.set_rgb(0, 0, 0):
                return False
            time.sleep(0.25)
        return True
    finally:
        # Leave the device as we found it: blank, and powered off again if it was
        # off before the test (don't surprise the user with a strip left on).
        try:
            drv.set_rgb(0, 0, 0)
            if was_on is False:
                drv.turn_off()
        finally:
            drv.disconnect()


@app.post("/api/devices/test", dependencies=[Depends(verify_token)])
async def test_device(request: DeviceTestRequest) -> Dict[str, str]:
    """Flash a device's LEDs so the user can confirm they picked the right one."""
    cfg = ConfigManager.get()
    protocol = (request.protocol or "magichome").strip().lower()
    # WLED's control is its HTTP API (port 80); MagicHome uses the configured TCP port.
    default_port = 80 if protocol == "wled" else cfg.device.port
    port = request.port or default_port
    ok = await asyncio.get_running_loop().run_in_executor(
        None, _flash_device, request.ip, port, protocol,
    )
    if not ok:
        raise HTTPException(status_code=502, detail=f"Could not reach device at {request.ip}:{port}")
    return {"message": f"Flashed device at {request.ip}"}


@app.get("/api/devices/{ip}/capabilities", dependencies=[Depends(verify_token)])
async def device_capabilities(ip: str, protocol: str = "magichome") -> Dict[str, Any]:
    """Live-probe a device and classify its capabilities (FR-DEV-04)."""
    cfg = ConfigManager.get()
    loop = asyncio.get_running_loop()

    protocol = protocol.strip().lower()
    if protocol == "wled":
        info = await loop.run_in_executor(None, _wled_probe, ip, cfg.device.connect_timeout)
        if info is None:
            raise HTTPException(status_code=502, detail=f"Could not reach WLED device at {ip}")
        return {
            "ip": info.ip, "mac": info.mac, "protocol": "wled",
            "kind": "addressable", "led_count": info.led_count,
            "supports_addressable": True, "supports_rgbw": False,
        }

    probe = CapabilityProbe(connect_timeout=cfg.device.connect_timeout)
    info = await loop.run_in_executor(None, probe.probe, ip, cfg.device.port)
    if info is None:
        raise HTTPException(status_code=502, detail=f"Could not reach device at {ip}")
    return {
        "ip": info.ip,
        "mac": info.mac,
        "protocol": "magichome",
        "device_type": info.device_type,
        "kind": classify_device(info),
        "supports_addressable": info.supports_addressable,
        "supports_rgbw": info.supports_rgbw,
    }


# ---------------------------------------------------------------------------
# OWNERSHIP ENDPOINTS (cross-instance device exclusivity)
# ---------------------------------------------------------------------------

class OwnershipActionRequest(pydantic.BaseModel):
    device_key: str
    force: bool = False   # claim only: out-prioritise the current owner ("take control")


@app.get("/api/ownership", dependencies=[Depends(verify_token)])
async def ownership_status() -> Dict[str, Any]:
    """This instance's identity plus the owner/claimants of every known device."""
    o = ConfigManager.get().ownership
    return {
        "enabled": bool(o.enabled),
        "instance_id": o.instance_id,
        "instance_label": o.instance_label,
        "transport": coordinator.transport_kind if coordinator is not None else None,
        "devices": coordinator.snapshot() if coordinator is not None else [],
    }


@app.post("/api/ownership/claim", dependencies=[Depends(verify_token)])
async def ownership_claim(request: OwnershipActionRequest) -> Dict[str, Any]:
    """Claim a device for this instance. ``force`` takes control from another
    instance that currently owns it."""
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ownership coordinator not running")
    owned = coordinator.claim(request.device_key, force=request.force)
    return {"device_key": request.device_key, "owned": owned}


@app.post("/api/ownership/release", dependencies=[Depends(verify_token)])
async def ownership_release(request: OwnershipActionRequest) -> Dict[str, Any]:
    """Release a device so another instance may take it over."""
    if coordinator is None:
        raise HTTPException(status_code=503, detail="ownership coordinator not running")
    coordinator.release(request.device_key)
    return {"device_key": request.device_key, "released": True}


# ---------------------------------------------------------------------------
# WEBSOCKET ENDPOINT
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


import time

last_ws_broadcast = 0.0
WS_BROADCAST_INTERVAL = 0.1  # 10Hz

async def push_metrics_to_ws(metrics: dict) -> None:
    """EventBus callback for METRICS_UPDATE"""
    global last_ws_broadcast
    now = time.monotonic()
    if now - last_ws_broadcast < WS_BROADCAST_INTERVAL:
        return
    last_ws_broadcast = now
    
    if manager.active_connections:
        await manager.broadcast(metrics)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token or token != auth._current_token:
        logger.warning("[API] Rejected WebSocket connection due to invalid token.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive. The client can send commands here if needed,
            # but currently we only use this for pushing metrics.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
