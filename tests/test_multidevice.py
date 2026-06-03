"""Tests for multi-device / multi-monitor config normalisation (FR-DEV-05, FR-CAP-06)."""

from ambilight.config import AppConfig
from ambilight.pipeline import _device_specs


def test_single_device_fallback():
    cfg = AppConfig()
    cfg.capture.monitor_index = 2
    specs = _device_specs(cfg)
    assert len(specs) == 1
    assert specs[0]["ip"] == cfg.device.ip
    assert specs[0]["monitor_index"] == 2   # inherits capture.monitor_index


def test_multi_device_list_used_when_present():
    cfg = AppConfig()
    cfg.devices = [
        {"ip": "192.168.1.10", "monitor_index": 0, "led_count": 30},
        {"ip": "192.168.1.11", "monitor_index": 1, "led_count": 60},
    ]
    specs = _device_specs(cfg)
    assert [s["ip"] for s in specs] == ["192.168.1.10", "192.168.1.11"]
    assert sorted({s["monitor_index"] for s in specs}) == [0, 1]
    assert specs[1]["led_count"] == 60


def test_disabled_devices_excluded():
    cfg = AppConfig()
    cfg.devices = [
        {"ip": "192.168.1.10", "enabled": True},
        {"ip": "192.168.1.11", "enabled": False},
    ]
    specs = _device_specs(cfg)
    assert [s["ip"] for s in specs] == ["192.168.1.10"]


def test_specs_inherit_device_defaults():
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50"}]   # minimal entry
    s = _device_specs(cfg)[0]
    assert s["port"] == cfg.device.port
    assert s["subnet"] == cfg.device.subnet
    assert s["name"] == "192.168.1.50"       # name defaults to ip


def test_distinct_monitor_grouping():
    cfg = AppConfig()
    cfg.devices = [
        {"ip": "a", "monitor_index": 0},
        {"ip": "b", "monitor_index": 0},   # shares monitor 0
        {"ip": "c", "monitor_index": 1},
    ]
    specs = _device_specs(cfg)
    distinct_monitors = sorted({s["monitor_index"] for s in specs})
    assert distinct_monitors == [0, 1]      # 3 devices, 2 capture sources
    assert len(specs) == 3
