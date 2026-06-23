"""
Home Assistant MQTT discovery (C2)
==================================
Builds the `Home Assistant MQTT discovery
<https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery>`_ config
payloads so Ambilight appears in HA — with no YAML — as one device exposing:

* a **light** (JSON schema: on/off, RGB colour, effect = the mode list),
* a **select** to apply lighting profiles,
* read-only **sensors**: FPS, syncing (binary), devices connected.

:func:`build_payloads` is pure (given a bridge's topics + a profile list) so it
unit-tests without a broker; :func:`publish` / :func:`remove` just serialize and
send them retained.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from .. import __version__ as APP_VERSION

DISCOVERY_PREFIX = "homeassistant"

# Modes surfaced to HA as light "effects". Excludes the internal ``static``
# (driven by the colour picker) and ``custom`` (needs a sequence param).
EFFECT_LIST = [
    "screen_sync", "rainbow", "breathing", "candle",
    "ocean", "ambient", "sunrise", "sunset", "audio",
]


def _node_id(bridge) -> str:
    """Stable, slug-safe HA node/device id from config device_id or hostname."""
    raw = (getattr(bridge._cfg, "device_id", "") or socket.gethostname() or "ambilight")
    slug = "".join(ch if ch.isalnum() else "_" for ch in str(raw).lower())
    return slug.strip("_") or "ambilight"


def _device(node: str) -> dict[str, Any]:
    return {
        "identifiers": [node],
        "name": "Ambilight",
        "manufacturer": "Ambilight",
        "model": "Ambilight Desktop",
        "sw_version": APP_VERSION,
    }


def build_payloads(bridge, profiles: list) -> dict[str, dict]:
    """Return ``{discovery_config_topic: payload}`` for every entity."""
    node = _node_id(bridge)
    dev = _device(node)
    avail = bridge.availability_topic
    return {
        f"{DISCOVERY_PREFIX}/light/{node}/config": {
            "schema": "json",
            "name": "Ambilight",
            "unique_id": f"{node}_light",
            "command_topic": bridge.light_command_topic,
            "state_topic": bridge.light_state_topic,
            "availability_topic": avail,
            "supported_color_modes": ["rgb"],
            "effect": True,
            "effect_list": list(EFFECT_LIST),
            "device": dev,
        },
        f"{DISCOVERY_PREFIX}/select/{node}_profile/config": {
            "name": "Ambilight Profile",
            "unique_id": f"{node}_profile",
            "command_topic": bridge.profile_command_topic,
            "state_topic": bridge.profile_state_topic,
            "availability_topic": avail,
            "options": list(profiles),
            "device": dev,
        },
        f"{DISCOVERY_PREFIX}/sensor/{node}_fps/config": {
            "name": "Ambilight FPS",
            "unique_id": f"{node}_fps",
            "state_topic": bridge.sensor_topic("fps"),
            "unit_of_measurement": "fps",
            "availability_topic": avail,
            "device": dev,
        },
        f"{DISCOVERY_PREFIX}/binary_sensor/{node}_syncing/config": {
            "name": "Ambilight Syncing",
            "unique_id": f"{node}_syncing",
            "state_topic": bridge.sensor_topic("syncing"),
            "payload_on": "ON",
            "payload_off": "OFF",
            "availability_topic": avail,
            "device": dev,
        },
        f"{DISCOVERY_PREFIX}/sensor/{node}_devices/config": {
            "name": "Ambilight Devices Connected",
            "unique_id": f"{node}_devices",
            "state_topic": bridge.sensor_topic("devices"),
            "availability_topic": avail,
            "device": dev,
        },
    }


def publish(bridge, client) -> None:
    """Publish retained discovery configs for all entities."""
    try:
        profiles = bridge._profiles.list_profiles()
    except Exception:
        profiles = []
    for topic, payload in build_payloads(bridge, profiles).items():
        client.publish(topic, json.dumps(payload), qos=1, retain=True)


def remove(bridge, client) -> None:
    """Remove the entities by publishing empty retained payloads to their config
    topics (Home Assistant deletes a discovered entity on an empty config)."""
    for topic in build_payloads(bridge, []):
        client.publish(topic, "", qos=1, retain=True)
