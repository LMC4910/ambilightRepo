"""Tests for device status parsing + capability classification (FR-DEV-02/04)."""

from ambilight.discovery import DeviceScanner, DeviceInfo, classify_device


def _status_bytes(device_type, mac_bytes):
    # 14-byte status: byte[1]=device_type, bytes[6:12]=MAC.
    data = bytearray(14)
    data[1] = device_type
    data[6:12] = bytes(mac_bytes)
    return bytes(data)


def test_parse_status_extracts_mac_and_type():
    mac_bytes = [0x30, 0x3a, 0x29, 0x00, 0x0c, 0x00]
    mac, firmware, dtype = DeviceScanner._parse_status(_status_bytes(0x33, mac_bytes))
    assert dtype == 0x33
    assert mac == "30:3a:29:00:0c:00"


def test_parse_status_short_data():
    mac, firmware, dtype = DeviceScanner._parse_status(b"\x00\x01")
    assert dtype == 0 and mac == ""


def test_classify_device():
    assert classify_device(DeviceInfo(ip="x", supports_addressable=True)) == "addressable"
    assert classify_device(DeviceInfo(ip="x", supports_rgbw=True)) == "rgbw"
    assert classify_device(DeviceInfo(ip="x")) == "single"
