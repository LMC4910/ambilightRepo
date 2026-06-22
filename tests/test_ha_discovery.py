"""Tests for Home Assistant MQTT discovery payloads (C2).

build_payloads is pure — these check topics, required keys, the shared device
block, and that removal publishes empty payloads. No broker."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from ambilight.integrations import ha_discovery


class _FakeBridge:
    """Minimal stand-in exposing the topic surface ha_discovery reads."""
    def __init__(self, device_id="deskpc", base="ambilight"):
        self._cfg = SimpleNamespace(device_id=device_id)
        self._base = base
        self._profiles = SimpleNamespace(list_profiles=lambda: ["gaming", "movie"])

    @property
    def availability_topic(self): return f"{self._base}/availability"
    @property
    def light_command_topic(self): return f"{self._base}/light/set"
    @property
    def light_state_topic(self): return f"{self._base}/light/state"
    @property
    def profile_command_topic(self): return f"{self._base}/profile/set"
    @property
    def profile_state_topic(self): return f"{self._base}/profile/state"
    def sensor_topic(self, key): return f"{self._base}/sensor/{key}"


def test_payloads_cover_all_entities():
    payloads = ha_discovery.build_payloads(_FakeBridge(), ["gaming", "movie"])
    topics = set(payloads)
    assert topics == {
        "homeassistant/light/deskpc/config",
        "homeassistant/select/deskpc_profile/config",
        "homeassistant/sensor/deskpc_fps/config",
        "homeassistant/binary_sensor/deskpc_syncing/config",
        "homeassistant/sensor/deskpc_devices/config",
    }


def test_light_payload_is_json_schema_with_effects():
    p = ha_discovery.build_payloads(_FakeBridge(), [])["homeassistant/light/deskpc/config"]
    assert p["schema"] == "json"
    assert p["supported_color_modes"] == ["rgb"]
    assert p["effect"] is True and "screen_sync" in p["effect_list"]
    assert "static" not in p["effect_list"] and "custom" not in p["effect_list"]
    assert p["command_topic"] == "ambilight/light/set"
    assert p["state_topic"] == "ambilight/light/state"


def test_select_lists_profiles():
    p = ha_discovery.build_payloads(_FakeBridge(), ["gaming", "movie"])["homeassistant/select/deskpc_profile/config"]
    assert p["options"] == ["gaming", "movie"]
    assert p["command_topic"] == "ambilight/profile/set"


def test_all_entities_share_one_device_and_availability():
    payloads = ha_discovery.build_payloads(_FakeBridge(), [])
    devices = {json.dumps(p["device"], sort_keys=True) for p in payloads.values()}
    assert len(devices) == 1                       # one HA device groups them
    dev = next(iter(payloads.values()))["device"]
    assert dev["identifiers"] == ["deskpc"] and dev["name"] == "Ambilight"
    assert all(p["availability_topic"] == "ambilight/availability" for p in payloads.values())


def test_unique_ids_are_distinct():
    payloads = ha_discovery.build_payloads(_FakeBridge(), [])
    uids = [p["unique_id"] for p in payloads.values()]
    assert len(uids) == len(set(uids))


def test_node_id_slugifies_device_id():
    b = _FakeBridge(device_id="Living Room PC!")
    p = ha_discovery.build_payloads(b, [])
    assert "homeassistant/light/living_room_pc/config" in p


def test_publish_and_remove(monkeypatch):
    client = MagicMock()
    bridge = _FakeBridge()
    ha_discovery.publish(bridge, client)
    pubs = {c.args[0]: c.args[1] for c in client.publish.call_args_list}
    assert "homeassistant/light/deskpc/config" in pubs
    assert json.loads(pubs["homeassistant/light/deskpc/config"])["schema"] == "json"

    client.publish.reset_mock()
    ha_discovery.remove(bridge, client)
    removed = {c.args[0]: c.args[1] for c in client.publish.call_args_list}
    assert removed["homeassistant/light/deskpc/config"] == ""   # empty = delete entity
    assert all(v == "" for v in removed.values())
