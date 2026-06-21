"""Tests for the WLED driver (A1).

All network is mocked — these cover the deterministic logic: realtime packet
framing (DRGB / chunked DNRGB), set_rgb filling the whole strip, JSON power
payloads, led_count discovery from /json/info, and is_addressable."""

import numpy as np  # noqa: F401  (kept parity with other tests; not required)

from ambilight.devices.wled import (
    WledDriver, build_realtime_packets, _REALTIME_PORT,
)
from ambilight.devices import LedDriver, create_driver


# --- packet framing -------------------------------------------------------

def test_drgb_packet_for_short_strip():
    pkts = build_realtime_packets([(10, 20, 30), (40, 50, 60)], timeout=2)
    assert len(pkts) == 1
    p = pkts[0]
    assert p[0] == 2 and p[1] == 2            # DRGB protocol byte + timeout
    assert p[2:] == bytes([10, 20, 30, 40, 50, 60])


def test_empty_pixels_yield_no_packets():
    assert build_realtime_packets([]) == []


def test_dnrgb_chunks_for_long_strip():
    pixels = [(1, 2, 3)] * 1000          # > 490 → DNRGB chunks of 489
    pkts = build_realtime_packets(pixels, timeout=2)
    assert len(pkts) == 3                # 489 + 489 + 22
    # First chunk starts at index 0.
    assert pkts[0][0] == 4 and pkts[0][1] == 2
    assert pkts[0][2] == 0 and pkts[0][3] == 0
    # Second chunk starts at index 489 (0x01E9).
    assert pkts[1][0] == 4
    assert (pkts[1][2] << 8 | pkts[1][3]) == 489
    # Body lengths line up with the chunk sizes.
    assert len(pkts[0]) == 4 + 489 * 3
    assert len(pkts[2]) == 4 + 22 * 3


def test_channel_masking():
    pkts = build_realtime_packets([(300, -1, 256)])  # values masked to a byte
    assert pkts[0][2:] == bytes([300 & 0xFF, (-1) & 0xFF, 256 & 0xFF])


# --- driver behavior (mocked I/O) -----------------------------------------

def _driver(monkeypatch, led_count=4):
    d = WledDriver(ip="1.2.3.4", led_count=led_count)
    sent = []
    monkeypatch.setattr(d, "_send_realtime", lambda px: (sent.append(list(px)) or True))
    return d, sent


def test_is_addressable_and_subclass():
    d = WledDriver(ip="1.2.3.4")
    assert isinstance(d, LedDriver)
    assert d.is_addressable is True


def test_set_rgb_fills_whole_strip(monkeypatch):
    d, sent = _driver(monkeypatch, led_count=5)
    assert d.set_rgb(7, 8, 9) is True
    assert sent == [[(7, 8, 9)] * 5]
    assert d.last_color == (7, 8, 9)


def test_set_rgb_dedupes_identical_color_when_connected(monkeypatch):
    d, sent = _driver(monkeypatch, led_count=3)
    d._connected = True               # dedup only applies while connected
    d.set_rgb(1, 2, 3)
    d._last_send_time = 0             # bypass the rate limiter
    assert d.set_rgb(1, 2, 3) is True
    assert len(sent) == 1            # second identical call suppressed


def test_set_rgb_resends_when_disconnected(monkeypatch):
    # Regression: a static scene must keep sending while disconnected so the
    # backoff reconnect in _send_realtime can recover (no dedup short-circuit).
    d, sent = _driver(monkeypatch, led_count=3)
    d._connected = False
    d.set_rgb(1, 2, 3)
    d._last_send_time = 0
    d.set_rgb(1, 2, 3)               # identical, but disconnected → still sent
    assert len(sent) == 2


def test_set_pixels_passes_through(monkeypatch):
    d, sent = _driver(monkeypatch)
    px = [(1, 1, 1), (2, 2, 2)]
    assert d.set_pixels(px) is True
    assert sent == [px]


def test_connect_reads_led_count(monkeypatch):
    d = WledDriver(ip="1.2.3.4", led_count=30)
    monkeypatch.setattr(d, "_http_get_json", lambda path: {"leds": {"count": 144}})
    monkeypatch.setattr(d, "_ensure_socket", lambda: None)
    assert d.connect() is True
    assert d.led_count == 144 and d.is_connected is True


def test_connect_failure_marks_disconnected(monkeypatch):
    d = WledDriver(ip="1.2.3.4")
    monkeypatch.setattr(d, "_http_get_json", lambda path: None)
    assert d.connect() is False
    assert d.is_connected is False


def test_power_uses_json_state(monkeypatch):
    d = WledDriver(ip="1.2.3.4")
    posts = []
    monkeypatch.setattr(d, "_http_post_json", lambda path, payload: (posts.append((path, payload)) or True))
    assert d.turn_on() is True and d.power_on is True
    assert d.turn_off() is True and d.power_on is False
    assert posts == [("/json/state", {"on": True}), ("/json/state", {"on": False})]


def test_factory_builds_wled_addressable():
    d = create_driver({"protocol": "wled", "ip": "1.2.3.4", "led_count": 120})
    assert isinstance(d, WledDriver)
    assert d.is_addressable is True and d.led_count == 120
    assert d._realtime_port == _REALTIME_PORT
