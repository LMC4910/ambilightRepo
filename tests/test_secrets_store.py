"""Tests for the keyring-backed secret store (C1a).

keyring is mocked — these verify the set/get/clear round-trip and the graceful
session fallback when keyring is unavailable or raises."""

from unittest.mock import MagicMock

import ambilight.integrations.secrets_store as ss


def setup_function(_):
    ss._fallback.clear()


def test_roundtrip_with_keyring(monkeypatch):
    store = {}
    fake = MagicMock()
    fake.set_password.side_effect = lambda svc, key, val: store.__setitem__((svc, key), val)
    fake.get_password.side_effect = lambda svc, key: store.get((svc, key))
    fake.delete_password.side_effect = lambda svc, key: store.pop((svc, key), None)
    monkeypatch.setattr(ss, "_keyring", lambda: fake)

    ss.set_mqtt_password("hunter2")
    assert ss.get_mqtt_password() == "hunter2"
    ss.clear_mqtt_password()
    assert ss.get_mqtt_password() == ""


def test_fallback_when_keyring_absent(monkeypatch):
    monkeypatch.setattr(ss, "_keyring", lambda: None)
    ss.set_mqtt_password("sekret")
    assert ss.get_mqtt_password() == "sekret"   # session fallback
    ss.clear_mqtt_password()
    assert ss.get_mqtt_password() == ""


def test_fallback_when_keyring_raises(monkeypatch):
    fake = MagicMock()
    fake.set_password.side_effect = RuntimeError("no backend")
    fake.get_password.side_effect = RuntimeError("no backend")
    monkeypatch.setattr(ss, "_keyring", lambda: fake)
    ss.set_mqtt_password("x")                    # set raises → falls back
    assert ss.get_mqtt_password() == "x"         # get raises → reads fallback


def test_missing_password_is_empty_string(monkeypatch):
    monkeypatch.setattr(ss, "_keyring", lambda: None)
    assert ss.get_mqtt_password() == ""
