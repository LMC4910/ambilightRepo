"""
MQTT ownership transport
========================
Coordination channel used when an MQTT broker is configured. Each instance
publishes its full claim list to a retained, per-instance topic
``{base}/ownership/instances/{instance_id}`` and subscribes to the wildcard so
it sees every peer. Retained messages mean a freshly-started instance learns the
existing owners immediately; a Last-Will clears our retained announcement if we
drop off the network, so a crashed owner's claims disappear.

Reuses the broker settings + ``paho``/keyring patterns from
:mod:`ambilight.integrations.mqtt_bridge` (opens its own client so it is
independent of whether the Home Assistant bridge is enabled).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _paho():
    """Return paho.mqtt.client if importable, else None (optional dependency)."""
    try:
        import paho.mqtt.client as mqtt  # optional dependency
        return mqtt
    except Exception:
        return None


class MqttTransport:
    """Per-instance retained-topic transport for ownership announcements."""

    def __init__(self, mqtt_cfg, instance_id: str, on_remote, get_password=None) -> None:
        self._cfg = mqtt_cfg
        self._id = instance_id
        self._on_remote = on_remote
        if get_password is None:
            from ..integrations import secrets_store
            get_password = secrets_store.get_mqtt_password
        self._get_password = get_password
        self._mqtt = _paho()
        self._client = None

    # ------------------------------------------------------------------ topics
    @property
    def _base(self) -> str:
        return (getattr(self._cfg, "base_topic", "") or "ambilight")

    def _instance_topic(self, instance_id: str) -> str:
        return f"{self._base}/ownership/instances/{instance_id}"

    @property
    def _self_topic(self) -> str:
        return self._instance_topic(self._id)

    @property
    def _wildcard(self) -> str:
        return f"{self._base}/ownership/instances/+"

    # --------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        if self._mqtt is None:
            logger.warning("[Ownership MQTT] paho-mqtt not installed; using LAN fallback.")
            return False
        if not str(getattr(self._cfg, "broker", "") or "").strip():
            return False
        try:
            client = self._make_client()
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            if getattr(self._cfg, "username", ""):
                client.username_pw_set(self._cfg.username, self._get_password() or None)
            if getattr(self._cfg, "tls", False):
                client.tls_set()
            # LWT: clear our retained announcement if we drop unexpectedly so a
            # crashed owner's claims expire for everyone immediately.
            client.will_set(self._self_topic, "", qos=1, retain=True)
            client.connect_async(self._cfg.broker, int(self._cfg.port), keepalive=60)
            client.loop_start()
            self._client = client
            logger.info("[Ownership MQTT] Connecting to %s:%s.", self._cfg.broker, self._cfg.port)
            return True
        except Exception as exc:
            logger.warning("[Ownership MQTT] connect failed: %s", exc)
            self._client = None
            return False

    def stop(self) -> None:
        if self._client is not None:
            try:
                # Clear our retained announcement so peers drop us cleanly.
                self._client.publish(self._self_topic, "", qos=1, retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:  # pragma: no cover - network teardown
                logger.debug("[Ownership MQTT] teardown error: %s", exc)
        self._client = None

    def publish(self, announcement: dict) -> None:
        if self._client is None:
            return
        try:
            self._client.publish(
                self._self_topic, json.dumps(announcement), qos=0, retain=True
            )
        except Exception as exc:  # pragma: no cover - network
            logger.debug("[Ownership MQTT] publish failed: %s", exc)

    # ----------------------------------------------------------------- paho cb
    def _make_client(self):
        mqtt = self._mqtt
        cid = f"ambilight-own-{self._id[:8]}"
        try:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=cid)  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            return mqtt.Client(client_id=cid)

    def _on_connect(self, client, _userdata, _flags, rc, *args) -> None:
        if rc != 0:
            logger.warning("[Ownership MQTT] broker refused connection (rc=%s).", rc)
            return
        try:
            client.subscribe(self._wildcard)
        except Exception as exc:  # pragma: no cover - network
            logger.debug("[Ownership MQTT] subscribe failed: %s", exc)

    def _on_message(self, _client, _userdata, msg) -> None:
        instance_id = msg.topic.rsplit("/", 1)[-1]
        try:
            payload = msg.payload.decode("utf-8").strip()
        except Exception:
            return
        # Empty retained payload == the peer cleared its announcement (clean exit
        # or LWT): treat as that instance going offline.
        if not payload:
            try:
                self._on_remote({"instance_id": instance_id, "_offline": True})
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[Ownership MQTT] offline handler error: %s", exc)
            return
        try:
            data = json.loads(payload)
        except ValueError:
            return
        if isinstance(data, dict):
            data.setdefault("instance_id", instance_id)
            try:
                self._on_remote(data)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[Ownership MQTT] handler error: %s", exc)
