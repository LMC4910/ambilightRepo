"""Tests for device status parsing, capability classification, and discovery helpers."""

from unittest.mock import MagicMock, patch

from ambilight.discovery import (
    DeviceScanner,
    DeviceInfo,
    classify_device,
    _local_subnets,
    _udp_discover,
)


def _status_bytes(device_type: int, power: int = 0x23) -> bytes:
    """
    Build a minimal valid MagicHome TCP status response.

    Layout: byte 0 = 0x81 (header), byte 1 = device_type, byte 2 = power,
    bytes 3-13 = zero padding.  Bytes 6-11 are RGB/W colour data, NOT MAC.
    """
    data = bytearray(14)
    data[0] = 0x81   # valid response header
    data[1] = device_type
    data[2] = power
    return bytes(data)


# ---------------------------------------------------------------------------
# _parse_status
# ---------------------------------------------------------------------------

def test_parse_status_extracts_device_type():
    """device_type is reliably at byte 1 of a valid MagicHome status response."""
    _, _, dtype = DeviceScanner._parse_status(_status_bytes(0x33))
    assert dtype == 0x33


def test_parse_status_returns_empty_mac():
    """MAC is NOT in the status response — _parse_status must always return ''."""
    mac, _, _ = DeviceScanner._parse_status(_status_bytes(0x44))
    assert mac == "", "MAC must come from UDP discovery, not from colour bytes"


def test_parse_status_invalid_header_returns_zero():
    """If byte 0 is not 0x81, the response is not a valid MagicHome status."""
    data = bytearray(14)
    data[0] = 0x00   # invalid header
    data[1] = 0x44
    _, _, dtype = DeviceScanner._parse_status(bytes(data))
    assert dtype == 0


def test_parse_status_minimum_valid():
    """A 2-byte response with correct header is the minimum valid form."""
    mac, _, dtype = DeviceScanner._parse_status(bytes([0x81, 0x44]))
    assert dtype == 0x44
    assert mac == ""


def test_parse_status_short_data():
    """Responses shorter than 2 bytes (or with wrong header) yield zeroes."""
    mac, firmware, dtype = DeviceScanner._parse_status(b"\x00")
    assert dtype == 0 and mac == ""


# ---------------------------------------------------------------------------
# classify_device
# ---------------------------------------------------------------------------

def test_classify_device():
    assert classify_device(DeviceInfo(ip="x", supports_addressable=True)) == "addressable"
    assert classify_device(DeviceInfo(ip="x", supports_rgbw=True)) == "rgbw"
    assert classify_device(DeviceInfo(ip="x")) == "single"


# ---------------------------------------------------------------------------
# _local_subnets
# ---------------------------------------------------------------------------

def test_local_subnets_returns_list():
    subnets = _local_subnets()
    assert isinstance(subnets, list)
    assert len(subnets) >= 1
    for s in subnets:
        # Each entry must be a /24 prefix like "192.168.1."
        assert s.endswith("."), f"Expected '.' suffix, got {s!r}"
        parts = s.rstrip(".").split(".")
        assert len(parts) == 3, f"Expected 3 octets, got {s!r}"


# ---------------------------------------------------------------------------
# _udp_discover — mock the socket so no real packets are sent
# ---------------------------------------------------------------------------

def test_udp_discover_parses_response():
    """UDP responses of the form 'IP,MACNOCOLONS,Model' are parsed correctly."""
    fake_response = b"192.168.1.29,0B0D23000C00,HF-LPB100-ZJ200"

    mock_sock = MagicMock()
    mock_sock.recvfrom.side_effect = [
        (fake_response, ("192.168.1.29", 48899)),
        socket_timeout := __import__("socket").timeout,
    ]
    # After the first call raises timeout, the loop will exit via monotonic check
    mock_sock.recvfrom.side_effect = [
        (fake_response, ("192.168.1.29", 48899)),
        __import__("socket").timeout("mock timeout"),
    ]

    with patch("ambilight.discovery.socket.socket", return_value=mock_sock):
        import time
        with patch("ambilight.discovery.time.monotonic", side_effect=[0.0, 0.0, 10.0]):
            devices = _udp_discover(timeout=2.0)

    assert len(devices) == 1
    d = devices[0]
    assert d.ip == "192.168.1.29"
    assert d.mac == "0b:0d:23:00:0c:00"
    assert d.model == "HF-LPB100-ZJ200"


def test_udp_discover_ignores_malformed_response():
    """Malformed UDP replies must be silently skipped."""
    mock_sock = MagicMock()
    mock_sock.recvfrom.side_effect = [
        (b"not,valid", ("192.168.1.1", 48899)),
        __import__("socket").timeout("done"),
    ]
    with patch("ambilight.discovery.socket.socket", return_value=mock_sock):
        with patch("ambilight.discovery.time.monotonic", side_effect=[0.0, 0.0, 10.0]):
            devices = _udp_discover(timeout=2.0)
    assert devices == []
