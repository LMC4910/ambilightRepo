"""Tests for the MQTT bridge (C1b).

paho-mqtt is mocked (and may be absent in CI) — these cover the deterministic
logic: no-op when disabled/paho-absent, command topics → control surface,
connect wiring, and throttled state publishing. No real broker."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

import ambilight.integrations.mqtt_bridge as mb
from ambilight.integrations.mqtt_bridge import MqttBridge
from ambilight.config import AppConfig


def _cfg(enabled=False, **mqtt):
    cfg = AppConfig()
    cfg.mqtt.enabled = enabled
    cfg.mqtt.broker = mqtt.get("broker", "localhost")
    cfg.mqtt.base_topic = mqtt.get("base_topic", "ambilight")
    cfg.mqtt.ha_discovery = mqtt.get("ha_discovery", False)
    return cfg


def _bridge(monkeypatch, *, enabled, with_paho, client=None):
    """Build a bridge with paho mocked (or absent) and a mock controller/profiles."""
    if with_paho:
        client = client or MagicMock()
        fake = MagicMock()
        fake.Client = MagicMock(return_value=client)
        monkeypatch.setattr(mb, "_paho", lambda: fake)
    else:
        monkeypatch.setattr(mb, "_paho", lambda: None)
    ctl = MagicMock()
    profiles = MagicMock()
    bridge = MqttBridge(_cfg(enabled=enabled), ctl, profiles=profiles,
                        event_bus=MagicMock(), get_password=lambda: "")
    return bridge, ctl, profiles, client


# --- no-op paths ----------------------------------------------------------

def test_disabled_does_not_connect(monkeypatch):
    bridge, _, _, _ = _bridge(monkeypatch, enabled=False, with_paho=True)
    bridge.start()
    assert bridge._client is None


def test_no_paho_is_noop(monkeypatch):
    bridge, _, _, _ = _bridge(monkeypatch, enabled=True, with_paho=False)
    bridge.start()
    assert bridge._client is None      # disabled gracefully without paho


# --- connect wiring -------------------------------------------------------

def test_connect_sets_will_and_subscribes(monkeypatch):
    client = MagicMock()
    bridge, _, _, _ = _bridge(monkeypatch, enabled=True, with_paho=True, client=client)
    bridge.start()
    assert bridge._client is client
    client.will_set.assert_called_once()
    client.connect_async.assert_called_once()
    client.loop_start.assert_called_once()

    # Simulate a successful broker connect callback.
    bridge._on_connect(client, None, None, 0)
    assert bridge._connected is True
    pubs = [c.args[0] for c in client.publish.call_args_list]
    assert bridge.availability_topic in pubs            # announced online
    subs = [c.args[0] for c in client.subscribe.call_args_list]
    assert bridge.light_command_topic in subs and bridge.profile_command_topic in subs


# --- command handling -----------------------------------------------------

def test_light_commands_map_to_controller(monkeypatch):
    bridge, ctl, _, _ = _bridge(monkeypatch, enabled=True, with_paho=True)
    bridge._handle_light_command(json.dumps({"state": "OFF"}))
    bridge._handle_light_command(json.dumps({"state": "ON", "color": {"r": 1, "g": 2, "b": 3}}))
    bridge._handle_light_command(json.dumps({"state": "ON", "effect": "rainbow"}))
    bridge._handle_light_command(json.dumps({"state": "ON"}))
    assert [c.args for c in ctl.set_mode.call_args_list] == [
        ("off", {}),
        ("static", {"r": 1, "g": 2, "b": 3}),
        ("rainbow", {}),
        ("screen_sync", {}),
    ]


def test_profile_command_applies_profile(monkeypatch):
    bridge, _, profiles, _ = _bridge(monkeypatch, enabled=True, with_paho=True)
    bridge._handle_profile_command("gaming")
    profiles.apply_profile.assert_called_once_with("gaming")


# --- state publishing -----------------------------------------------------

def test_on_metrics_publishes_state_and_throttles(monkeypatch):
    client = MagicMock()
    bridge, _, profiles, _ = _bridge(monkeypatch, enabled=True, with_paho=True, client=client)
    profiles.active_profile = "gaming"
    bridge.start()
    bridge._on_connect(client, None, None, 0)
    client.publish.reset_mock()

    m = {"power": True, "mode": "screen_sync", "color": [10, 20, 30],
         "fps": 29.4, "devices_connected": 2, "capture_ok": True}
    asyncio.run(bridge.on_metrics(m))
    topics = {c.args[0]: c.args[1] for c in client.publish.call_args_list}
    assert bridge.light_state_topic in topics
    light = json.loads(topics[bridge.light_state_topic])
    assert light["state"] == "ON" and light["color"] == {"r": 10, "g": 20, "b": 30}
    assert light["effect"] == "screen_sync"
    assert topics[bridge.sensor_topic("syncing")] == "ON"
    assert topics[bridge.sensor_topic("devices")] == "2"
    assert topics[bridge.profile_state_topic] == "gaming"

    # Identical metrics within the throttle window → suppressed.
    client.publish.reset_mock()
    asyncio.run(bridge.on_metrics(m))
    assert client.publish.call_count == 0


def test_connect_publishes_ha_discovery_when_enabled(monkeypatch):
    client = MagicMock()
    fake = MagicMock()
    fake.Client = MagicMock(return_value=client)
    monkeypatch.setattr(mb, "_paho", lambda: fake)
    cfg = _cfg(enabled=True, ha_discovery=True)
    profiles = MagicMock()
    profiles.list_profiles.return_value = ["gaming"]
    bridge = MqttBridge(cfg, MagicMock(), profiles=profiles, event_bus=MagicMock(), get_password=lambda: "")
    bridge.start()
    bridge._on_connect(client, None, None, 0)
    pubs = [c.args[0] for c in client.publish.call_args_list]
    assert any(t.startswith("homeassistant/light/") for t in pubs)
    assert any(t.startswith("homeassistant/select/") for t in pubs)


def test_on_metrics_noop_when_not_connected(monkeypatch):
    bridge, _, _, _ = _bridge(monkeypatch, enabled=True, with_paho=True)
    # not connected yet
    asyncio.run(bridge.on_metrics({"power": True, "mode": "screen_sync"}))
    # nothing to assert beyond "no exception"; _client may be set but _connected False
    assert bridge._connected is False
