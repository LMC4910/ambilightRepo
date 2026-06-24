"""Tests for multi-device / multi-monitor config normalisation (FR-DEV-05, FR-CAP-06)."""

from ambilight.config import AppConfig
from ambilight.pipeline import _device_specs, AmbilightPipeline


def test_single_device_fallback():
    cfg = AppConfig()
    cfg.capture.monitor_index = 2
    specs = _device_specs(cfg)
    assert len(specs) == 1
    assert specs[0]["ip"] == cfg.device.ip
    assert specs[0]["monitor_index"] == 2   # inherits capture.monitor_index


def test_single_device_prefers_device_monitor_id():
    # device.monitor_id wins over the global capture.monitor_id (matches the
    # multi-device path); otherwise setting it would be silently ignored.
    cfg = AppConfig()
    cfg.capture.monitor_id = "CAP-ID"
    cfg.device.monitor_id = "DEV-ID"
    assert _device_specs(cfg)[0]["monitor_id"] == "DEV-ID"


def test_single_device_falls_back_to_capture_monitor_id():
    cfg = AppConfig()
    cfg.capture.monitor_id = "CAP-ID"
    cfg.device.monitor_id = ""
    assert _device_specs(cfg)[0]["monitor_id"] == "CAP-ID"


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


def test_wled_device_without_port_defaults_to_http_80():
    # Regression: a UI/onboarding-added WLED entry persists no port, so it would
    # inherit the legacy MagicHome default 5577 and the pipeline would probe the
    # wrong HTTP port. It must resolve to WLED's HTTP API port 80.
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "protocol": "wled", "led_count": 120}]
    s = _device_specs(cfg)[0]
    assert s["protocol"] == "wled"
    assert s["port"] == 80


def test_wled_device_honours_explicit_port():
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "protocol": "wled", "port": 8080}]
    assert _device_specs(cfg)[0]["port"] == 8080


def test_magichome_device_keeps_default_port():
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.10"}]   # protocol defaults to magichome
    assert _device_specs(cfg)[0]["port"] == cfg.device.port  # 5577


def test_single_wled_device_defaults_to_http_80():
    cfg = AppConfig()
    cfg.device.protocol = "wled"   # legacy single-device path, port still 5577
    s = _device_specs(cfg)[0]
    assert s["protocol"] == "wled"
    assert s["port"] == 80


def test_topology_sig_changes_when_protocol_changes():
    # Regression: switching only the Protocol dropdown must rebuild I/O (a new
    # driver), so it has to alter the topology signature.
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "protocol": "magichome", "led_count": 30}]
    p = AmbilightPipeline(config=cfg)
    before = p._topology_sig()
    cfg.devices[0]["protocol"] = "wled"
    assert p._topology_sig() != before


def test_topology_sig_changes_when_port_changes():
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "protocol": "wled"}]   # port → 80
    p = AmbilightPipeline(config=cfg)
    before = p._topology_sig()
    cfg.devices[0]["port"] = 8080
    assert p._topology_sig() != before


def test_topology_sig_changes_when_wled_ip_changes_with_mac():
    # WLED has no MAC-based rediscovery, so it's keyed by IP: changing a WLED
    # device's IP must rebuild even when a MAC is present.
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff", "protocol": "wled"}]
    p = AmbilightPipeline(config=cfg)
    before = p._topology_sig()
    cfg.devices[0]["ip"] = "192.168.1.99"
    assert p._topology_sig() != before


def test_topology_sig_magichome_keyed_by_mac_not_ip():
    # MagicHome is MAC-stable: an IP change with the same MAC must NOT rebuild
    # (discovery recovers it), preserving the existing behaviour.
    cfg = AppConfig()
    cfg.devices = [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff", "protocol": "magichome"}]
    p = AmbilightPipeline(config=cfg)
    before = p._topology_sig()
    cfg.devices[0]["ip"] = "192.168.1.99"
    assert p._topology_sig() == before


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
