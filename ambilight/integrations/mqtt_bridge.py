"""
MQTT bridge (C1)
================
Publishes live Ambilight state to an MQTT broker and accepts commands, so the
app can be driven from Home Assistant or any MQTT client. Off by default;
``paho-mqtt`` is an optional dependency — when it's absent the bridge is a no-op
(mirrors the zeroconf/soundcard pattern).

Design
------
* paho runs its own network thread (``loop_start``). Its ``on_connect`` /
  ``on_message`` callbacks fire on that thread; anything async (event-bus
  publish, profile apply → ``CONFIG_UPDATE``) is hopped onto the captured
  asyncio loop with ``run_coroutine_threadsafe``. ``controller.set_mode`` is
  already queue-backed and thread-safe, so it's called directly.
* State is published from the ``METRICS_UPDATE`` subscriber, throttled to avoid
  flooding the broker at the capture frame rate.

Lifecycle mirrors :class:`~ambilight.auto_profile.AutoProfileSwitcher`:
``start()`` / ``stop()`` / ``update_config(cfg)``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from . import secrets_store

logger = logging.getLogger(__name__)

# Publish state at most this often (seconds) unless it changed — keeps a 30 fps
# pipeline from hammering the broker.
_STATE_MIN_INTERVAL = 1.0


def _paho():
    """Return paho.mqtt.client if importable, else None (optional dependency)."""
    try:
        import paho.mqtt.client as mqtt  # optional dependency
        return mqtt
    except Exception:
        return None


class MqttBridge:
    """Bridges the service's control surface + state to an MQTT broker."""

    def __init__(self, cfg, controller, *, profiles=None, event_bus=None, get_password=None) -> None:
        self._controller = controller
        if profiles is None:
            from ..profile_manager import profile_manager
            profiles = profile_manager
        self._profiles = profiles
        if event_bus is None:
            from ..events import bus
            event_bus = bus
        self._bus = event_bus
        self._get_password = get_password or secrets_store.get_mqtt_password

        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connected = False
        self._last_pub = 0.0
        self._last_payload: Optional[str] = None
        self._mqtt = _paho()
        self._cfg = None          # current MqttConfig snapshot
        self.update_config(cfg)

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------
    @property
    def base(self) -> str:
        return (self._cfg.base_topic or "ambilight") if self._cfg else "ambilight"

    @property
    def availability_topic(self) -> str:
        return f"{self.base}/availability"

    @property
    def light_state_topic(self) -> str:
        return f"{self.base}/light/state"

    @property
    def light_command_topic(self) -> str:
        return f"{self.base}/light/set"

    @property
    def profile_state_topic(self) -> str:
        return f"{self.base}/profile/state"

    @property
    def profile_command_topic(self) -> str:
        return f"{self.base}/profile/set"

    def sensor_topic(self, key: str) -> str:
        return f"{self.base}/sensor/{key}"

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def update_config(self, cfg) -> None:
        """Adopt the latest MqttConfig; reconnect if anything connection-affecting
        changed. Safe to call before/after start()."""
        new = cfg.mqtt
        old = self._cfg
        self._cfg = new
        # Before start() there's no loop yet — just store the config.
        if self._loop is None:
            return
        changed = old is None or (
            old.enabled != new.enabled or old.broker != new.broker or old.port != new.port
            or old.username != new.username or old.tls != new.tls or old.base_topic != new.base_topic
            or old.ha_discovery != new.ha_discovery or old.device_id != new.device_id
        )
        if changed:
            self._reconnect()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Capture the running loop and connect if enabled."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._reconnect()

    def stop(self) -> None:
        """Disconnect and tear down the client."""
        self._teardown_client()

    def _teardown_client(self) -> None:
        if self._client is not None:
            try:
                # Best-effort graceful offline before dropping the socket.
                self._client.publish(self.availability_topic, "offline", qos=1, retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:  # pragma: no cover - network teardown
                logger.debug("[MQTT] teardown error: %s", exc)
        self._client = None
        self._connected = False

    def _reconnect(self) -> None:
        self._teardown_client()
        if not (self._cfg and self._cfg.enabled):
            return
        if self._mqtt is None:
            logger.warning("[MQTT] paho-mqtt not installed; MQTT bridge disabled.")
            return
        if not str(self._cfg.broker).strip():
            return
        try:
            client = self._make_client()
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            if self._cfg.username:
                client.username_pw_set(self._cfg.username, self._get_password() or None)
            if self._cfg.tls:
                client.tls_set()
            client.will_set(self.availability_topic, "offline", qos=1, retain=True)
            client.connect_async(self._cfg.broker, int(self._cfg.port), keepalive=60)
            client.loop_start()
            self._client = client
            logger.info("[MQTT] Connecting to %s:%s (base topic '%s').",
                        self._cfg.broker, self._cfg.port, self.base)
        except Exception as exc:
            logger.warning("[MQTT] Connect failed: %s", exc)
            self._client = None

    def _make_client(self):
        mqtt = self._mqtt
        # paho-mqtt 2.x requires a callback API version; 1.x doesn't have it.
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)  # type: ignore[attr-defined]
        except AttributeError:
            return mqtt.Client()

    # ------------------------------------------------------------------
    # paho callbacks (run on paho's network thread)
    # ------------------------------------------------------------------
    def _on_connect(self, client, _userdata, _flags, rc, *args) -> None:
        if rc != 0:
            logger.warning("[MQTT] Broker refused connection (rc=%s).", rc)
            return
        self._connected = True
        logger.info("[MQTT] Connected.")
        client.publish(self.availability_topic, "online", qos=1, retain=True)
        client.subscribe(self.light_command_topic)
        client.subscribe(self.profile_command_topic)
        self._publish_discovery()
        # Force a fresh state publish on (re)connect.
        self._last_payload = None
        self._last_pub = 0.0

    def _on_message(self, _client, _userdata, msg) -> None:
        try:
            payload = msg.payload.decode("utf-8").strip()
        except Exception:
            return
        try:
            if msg.topic == self.light_command_topic:
                self._handle_light_command(payload)
            elif msg.topic == self.profile_command_topic:
                self._handle_profile_command(payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[MQTT] command error on %s: %s", msg.topic, exc)

    # ------------------------------------------------------------------
    # Command handling → control surface
    # ------------------------------------------------------------------
    def _handle_light_command(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            # Allow a bare ON/OFF too.
            data = {"state": payload}
        state = str(data.get("state", "")).upper()
        if state == "OFF":
            self._controller.set_mode("off", {})
            return
        # An explicit effect (mode) wins; then a colour (static); else just power on.
        effect = data.get("effect")
        color = data.get("color")
        if effect:
            self._controller.set_mode(str(effect), {})
        elif isinstance(color, dict) and {"r", "g", "b"} <= set(color):
            self._controller.set_mode("static", {
                "r": int(color["r"]), "g": int(color["g"]), "b": int(color["b"]),
            })
        else:
            self._controller.set_mode("screen_sync", {})

    def _handle_profile_command(self, name: str) -> None:
        if not name:
            return
        ok = self._profiles.apply_profile(name)
        if ok is False:
            logger.warning("[MQTT] profile '%s' not applied.", name)
            return
        # Profile apply mutates config but doesn't itself publish CONFIG_UPDATE
        # (the REST endpoint does); push it so the pipeline hot-reloads.
        self._run_on_loop(self._publish_config_update())

    async def _publish_config_update(self) -> None:
        from ..config import ConfigManager
        await self._bus.publish("CONFIG_UPDATE", ConfigManager.get())

    def _run_on_loop(self, coro) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:  # pragma: no cover - no loop in tests
            coro.close()

    # ------------------------------------------------------------------
    # State publishing (METRICS_UPDATE subscriber, runs on the loop)
    # ------------------------------------------------------------------
    async def on_metrics(self, metrics: dict) -> None:
        if not (self._client and self._connected):
            return
        now = time.monotonic()
        payload = self._light_state_payload(metrics)
        unchanged = payload == self._last_payload
        if unchanged and (now - self._last_pub) < _STATE_MIN_INTERVAL:
            return
        self._last_pub = now
        self._last_payload = payload
        try:
            self._client.publish(self.light_state_topic, payload, qos=0, retain=True)
            self._client.publish(self.profile_state_topic,
                                 getattr(self._profiles, "active_profile", None) or "", qos=0, retain=True)
            for key, val in self._sensor_values(metrics).items():
                self._client.publish(self.sensor_topic(key), val, qos=0, retain=True)
        except Exception as exc:  # pragma: no cover - network
            logger.debug("[MQTT] publish failed: %s", exc)

    def _light_state_payload(self, metrics: dict) -> str:
        power = bool(metrics.get("power", True))
        color = metrics.get("color", [0, 0, 0]) or [0, 0, 0]
        mode = metrics.get("mode", "screen_sync")
        state: dict[str, Any] = {"state": "ON" if power else "OFF"}
        if power:
            state["color_mode"] = "rgb"
            state["color"] = {"r": int(color[0]), "g": int(color[1]), "b": int(color[2])}
            state["effect"] = mode
        return json.dumps(state, sort_keys=True)

    def _sensor_values(self, metrics: dict) -> dict[str, str]:
        syncing = (
            bool(metrics.get("power", True))
            and metrics.get("mode") == "screen_sync"
            and bool(metrics.get("capture_ok", True))
        )
        return {
            "fps": f"{float(metrics.get('fps', 0.0)):.1f}",
            "syncing": "ON" if syncing else "OFF",
            "devices": str(int(metrics.get("devices_connected", 0))),
        }

    # ------------------------------------------------------------------
    # Home Assistant discovery (implemented in C2; no-op until then)
    # ------------------------------------------------------------------
    def _publish_discovery(self) -> None:
        if not (self._cfg and self._cfg.ha_discovery and self._client):
            return
        try:
            from . import ha_discovery
        except Exception:
            return
        ha_discovery.publish(self, self._client)
