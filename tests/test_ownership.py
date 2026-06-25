"""Tests for cross-instance device ownership.

Covers the deterministic logic — instance identity minting, the winner
tie-break, TTL expiry, force-takeover/release, transport selection, and the
pipeline's ownership gate — without real sockets, brokers, or capture hardware.
"""

import time
from unittest.mock import MagicMock

from ambilight.config import AppConfig, ConfigManager
from ambilight.pipeline import device_key, _Channel, AmbilightPipeline
from ambilight.ownership.coordinator import OwnershipCoordinator


# --------------------------------------------------------------------------- #
# Config: identity minting + timing clamps
# --------------------------------------------------------------------------- #

def test_instance_id_minted_and_persisted(tmp_path):
    path = tmp_path / "configuration.yaml"
    cfg = ConfigManager.load(path)
    iid = cfg.ownership.instance_id
    assert iid and len(iid) >= 8           # a real id was minted
    assert cfg.ownership.instance_label    # label defaults to hostname
    assert path.exists()                   # minted id was persisted to disk

    # Reload from the same file → the id is stable across "restarts".
    cfg2 = ConfigManager.load(path)
    assert cfg2.ownership.instance_id == iid


def test_ttl_floored_to_twice_heartbeat(tmp_path):
    path = tmp_path / "configuration.yaml"
    path.write_text("ownership:\n  heartbeat_interval: 10\n  ttl: 5\n", encoding="utf-8")
    cfg = ConfigManager.load(path)
    # A ttl below 2× the heartbeat would expire a live owner between beats.
    assert cfg.ownership.ttl >= 20.0


# --------------------------------------------------------------------------- #
# Device keying
# --------------------------------------------------------------------------- #

def test_device_key_magichome_by_mac_wled_by_ip():
    assert device_key({"protocol": "magichome", "mac": "AA:BB:CC", "ip": "1.2.3.4"}) == "magichome:aa:bb:cc"
    # No MAC → fall back to IP.
    assert device_key({"protocol": "magichome", "mac": "", "ip": "1.2.3.4"}) == "magichome:1.2.3.4"
    # WLED always keys by IP, even if a MAC is present.
    assert device_key({"protocol": "wled", "mac": "AA:BB", "ip": "1.2.3.4"}) == "wled:1.2.3.4"


# --------------------------------------------------------------------------- #
# Coordinator helpers
# --------------------------------------------------------------------------- #

K = "magichome:aa:bb:cc"


def _coord(*, enabled=True, instance_id="B", priority=0, desired=(K,), hb=1.0, ttl=30.0):
    cfg = AppConfig()
    o = cfg.ownership
    o.enabled, o.instance_id, o.instance_label = enabled, instance_id, instance_id
    o.priority, o.heartbeat_interval, o.ttl = priority, hb, ttl
    c = OwnershipCoordinator(cfg, event_bus=MagicMock(), get_password=lambda: "")
    c._desired = set(desired)
    return c


def _inject_peer(c, instance_id, key=K, priority=0, claimed_at=100.0):
    """Simulate receiving a peer announcement on a transport thread."""
    c._on_remote({
        "instance_id": instance_id, "instance_label": instance_id, "ts": 0.0,
        "claims": [{"device_key": key, "priority": priority, "claimed_at": claimed_at}],
    })


# --------------------------------------------------------------------------- #
# Winner resolution (priority → earliest claim → lowest id)
# --------------------------------------------------------------------------- #

def test_earliest_claim_wins_when_priority_equal():
    c = _coord(instance_id="B")
    c._claimed_at[K] = 200.0                 # we claimed later
    _inject_peer(c, "A", claimed_at=100.0)   # A claimed earlier
    assert c.owns(K) is False
    assert c.owner_of(K)["instance_id"] == "A"


def test_higher_priority_beats_earlier_claim():
    c = _coord(instance_id="B", priority=5)
    c._claimed_at[K] = 200.0                 # later, but higher priority
    _inject_peer(c, "A", priority=0, claimed_at=100.0)
    assert c.owns(K) is True


def test_lowest_id_breaks_exact_tie():
    c = _coord(instance_id="B")
    c._claimed_at[K] = 100.0
    _inject_peer(c, "A", priority=0, claimed_at=100.0)  # identical priority + claim time
    assert c.owns(K) is False                # "A" < "B"
    assert c.owner_of(K)["instance_id"] == "A"


def test_uncontested_device_is_owned():
    c = _coord(instance_id="B")
    assert c.owns(K) is True
    assert c.owner_of(K)["is_self"] is True


# --------------------------------------------------------------------------- #
# Liveness / TTL
# --------------------------------------------------------------------------- #

def test_stale_owner_claim_is_ignored():
    c = _coord(instance_id="B", ttl=30.0)
    c._claimed_at[K] = 200.0
    _inject_peer(c, "A", claimed_at=100.0)   # A owns it (earlier)
    assert c.owns(K) is False
    # A goes silent past the TTL → its claim no longer counts; we take over.
    c._peers["A"]["seen"] = time.monotonic() - 10_000
    assert c.owns(K) is True


# --------------------------------------------------------------------------- #
# Disabled = legacy behaviour
# --------------------------------------------------------------------------- #

def test_disabled_owns_everything():
    c = _coord(enabled=False)
    _inject_peer(c, "A", claimed_at=1.0)     # even with a competitor present
    assert c.owns(K) is True
    assert c.owns("magichome:whatever") is True
    assert c.owner_of(K)["is_self"] is True


# --------------------------------------------------------------------------- #
# Force takeover + release
# --------------------------------------------------------------------------- #

def test_force_takeover_wins_contested_device():
    c = _coord(instance_id="B")
    c._claimed_at[K] = 200.0
    _inject_peer(c, "A", priority=3, claimed_at=100.0)
    assert c.owns(K) is False
    assert c.claim(K, force=True) is True    # "take control"
    assert c.owns(K) is True


def test_release_yields_device():
    c = _coord(instance_id="B")
    assert c.owns(K) is True
    c.release(K)
    assert c.owns(K) is False                # no longer claiming it


# --------------------------------------------------------------------------- #
# Transport selection (auto-detect)
# --------------------------------------------------------------------------- #

def test_wanted_transport_prefers_mqtt_when_broker_set():
    c = _coord()
    c._cfg.mqtt.enabled = True
    c._cfg.mqtt.broker = "broker.local"
    assert c._wanted_transport() == "mqtt"


def test_wanted_transport_falls_back_to_lan():
    c = _coord()
    c._cfg.mqtt.enabled = False
    c._cfg.mqtt.broker = ""
    assert c._wanted_transport() == "lan"


# --------------------------------------------------------------------------- #
# Owned-set publishing (change detection + force)
# --------------------------------------------------------------------------- #

def test_recompute_publishes_only_on_change_unless_forced():
    c = _coord(instance_id="B")
    c._publish_owned = MagicMock()
    c._recompute_and_publish()                       # empty → {K}: a change
    c._publish_owned.assert_called_once()
    assert set(c._publish_owned.call_args[0][0]) == {K}

    c._publish_owned.reset_mock()
    c._recompute_and_publish()                       # unchanged → no emit
    c._publish_owned.assert_not_called()

    c._recompute_and_publish(force=True)             # forced re-emit (respawn catch-up)
    c._publish_owned.assert_called_once()


# --------------------------------------------------------------------------- #
# Two-instance convergence (the core scenario)
# --------------------------------------------------------------------------- #

def test_two_instances_agree_on_single_owner():
    """System A and System B both want the same strip → exactly one drives it,
    and both independently agree on which one (no sockets, just cross-fed
    announcements)."""
    a = _coord(instance_id="A")
    b = _coord(instance_id="B")
    a._claimed_at[K] = 100.0      # A linked the light first
    b._claimed_at[K] = 200.0      # B started later

    # Exchange what each instance would broadcast.
    b._on_remote(a._self_announcement())
    a._on_remote(b._self_announcement())

    assert a.owns(K) is True
    assert b.owns(K) is False     # B stands by — System B's signals never reach the strip
    assert a.owner_of(K)["instance_id"] == "A"
    assert b.owner_of(K)["instance_id"] == "A"


# --------------------------------------------------------------------------- #
# Pipeline ownership gate
# --------------------------------------------------------------------------- #

def _pipeline(enabled=True):
    cfg = AppConfig()
    cfg.ownership.enabled = enabled
    cfg.ownership.instance_id = "X"
    return AmbilightPipeline(config=cfg)


def test_is_owned_gate():
    p = _pipeline(enabled=True)
    p._ownership_enabled = True
    p._owned_keys = None
    assert p._is_owned("k") is False                 # stand by until told
    p._owned_keys = {"k"}
    assert p._is_owned("k") is True
    assert p._is_owned("other") is False
    p._ownership_enabled = False
    assert p._is_owned("anything") is True           # disabled → drive all


def test_apply_owned_connects_and_disconnects():
    p = _pipeline(enabled=True)
    p._ownership_enabled = True
    p._owned_keys = None
    led = MagicMock()
    led.is_connected = False
    led.connect.return_value = True
    ch = _Channel(
        name="d", monitor_index=0, led=led,
        zones=MagicMock(), analyzer=MagicMock(), smoother=MagicMock(),
        led_count=30, key="magichome:aa", owned=False,
    )
    p._channels = [ch]

    assert p._owned_channels() == []                 # standby: not driven

    p._apply_owned({"magichome:aa"})                 # we acquire it
    assert ch.owned is True
    led.connect.assert_called_once()
    assert p._owned_channels() == [ch]

    p._apply_owned(set())                            # we lose it
    assert ch.owned is False
    led.disconnect.assert_called_once()
    assert p._owned_channels() == []
