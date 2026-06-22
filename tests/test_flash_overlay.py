"""Tests for the pipeline notification-flash overlay state machine."""

import queue

import pytest

from ambilight.config import AppConfig
from ambilight.pipeline import AmbilightPipeline


class FakeLed:
    def __init__(self, addressable=False):
        self._addressable = addressable
        self.rgb_calls = []
        self.pixel_calls = []
        self.ensure_on_calls = 0
        self.turn_off_calls = 0

    @property
    def is_addressable(self):
        return self._addressable

    def set_rgb(self, r, g, b):
        self.rgb_calls.append((r, g, b))
        return True

    def set_pixels(self, pixels):
        self.pixel_calls.append(list(pixels))
        return True

    def ensure_on(self):
        self.ensure_on_calls += 1
        return True

    def turn_off(self):
        self.turn_off_calls += 1
        return True


class FakeChannel:
    def __init__(self, led, led_count=30):
        self.led = led
        self.led_count = led_count


def _pipeline(addressable=False):
    p = AmbilightPipeline(config=AppConfig())
    led = FakeLed(addressable=addressable)
    p._channels = [FakeChannel(led)]
    return p, led


def _flash(p, color=(10, 20, 30), blink_count=2, on_ms=100, off_ms=50, brightness=1.0):
    p._enqueue_flash(list(color), {
        "blink_count": blink_count, "on_ms": on_ms, "off_ms": off_ms, "brightness": brightness,
    })


def test_enqueue_builds_segments():
    p, _ = _pipeline()
    _flash(p, blink_count=2, on_ms=100, off_ms=50)
    seg = p._flash_queue[-1]["segments"]
    # on, off, on  (trailing off omitted)
    assert [s["on"] for s in seg] == [True, False, True]


def test_active_directive_sequence_and_finish():
    p, led = _pipeline()
    _flash(p, color=(10, 20, 30), blink_count=2, on_ms=0.1 * 1000, off_ms=0.05 * 1000)
    # on-segment
    assert p._flash_step(0.0, paused=False) == ("on", (10, 20, 30))
    assert led.ensure_on_calls == 1
    # still on at 0.05
    assert p._flash_step(0.05, paused=False) == ("on", (10, 20, 30))
    # off-segment after 0.1
    assert p._flash_step(0.11, paused=False) == ("off",)
    # second on-segment after 0.15
    assert p._flash_step(0.16, paused=False) == ("on", (10, 20, 30))
    # finished after total duration
    assert p._flash_step(0.30, paused=False) == ("inactive",)
    assert p._flash_active is None


def test_brightness_scales_color():
    p, _ = _pipeline()
    _flash(p, color=(200, 100, 50), brightness=0.5)
    d = p._flash_step(0.0, paused=False)
    assert d == ("on", (100, 50, 25))


def test_idle_flash_paints_and_restores_frozen_frame():
    p, led = _pipeline()
    p._power = True
    p._last_output_rgb = (5, 6, 7)
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    # on-segment paints the flash colour
    assert p._service_idle_flash(0.0) is True
    assert led.rgb_calls[-1] == (40, 41, 42)
    # after it ends, the frozen frame is restored (paused path)
    assert p._service_idle_flash(0.20) is False
    assert led.rgb_calls[-1] == (5, 6, 7)


def test_idle_flash_off_segment_paints_black():
    p, led = _pipeline()
    p._power = True
    _flash(p, color=(40, 41, 42), blink_count=2, on_ms=100, off_ms=100)
    p._service_idle_flash(0.0)               # on
    assert led.rgb_calls[-1] == (40, 41, 42)
    p._service_idle_flash(0.11)              # off → black
    assert led.rgb_calls[-1] == (0, 0, 0)


def test_powered_off_flash_restores_off():
    p, led = _pipeline()
    p._power = False                          # strip nominally off
    _flash(p, color=(9, 9, 9), blink_count=1, on_ms=100, off_ms=0)
    p._service_idle_flash(0.0)               # wakes + paints
    assert led.ensure_on_calls == 1
    p._service_idle_flash(0.20)              # ends → powers back off
    assert led.turn_off_calls == 1


def test_addressable_uses_set_pixels():
    p, led = _pipeline(addressable=True)
    p._power = True
    _flash(p, color=(1, 2, 3), blink_count=1, on_ms=100, off_ms=0)
    p._service_idle_flash(0.0)
    assert led.pixel_calls[-1] == [(1, 2, 3)] * 30   # channel led_count


def test_queue_coalesces_bursts():
    p, _ = _pipeline()
    for _ in range(5):
        _flash(p)
    assert len(p._flash_queue) == 3          # deque(maxlen=3)


def test_drain_flash_commands_acts_on_flash_defers_others():
    p, _ = _pipeline()
    q = queue.Queue()
    p._command_queue = q
    q.put({"action": "set_mode", "mode": "rainbow", "params": {}})
    q.put({"action": "flash", "color": [1, 2, 3], "pattern": {}})
    p._drain_flash_commands(enqueue=True)
    # flash was enqueued onto the overlay queue
    assert len(p._flash_queue) == 1
    # the set_mode command survived for processing on resume
    remaining = q.get_nowait()
    assert remaining["action"] == "set_mode"


def test_drain_flash_commands_drops_when_disabled():
    p, _ = _pipeline()
    q = queue.Queue()
    p._command_queue = q
    q.put({"action": "flash", "color": [1, 2, 3], "pattern": {}})
    p._drain_flash_commands(enqueue=False)
    assert len(p._flash_queue) == 0          # dropped, not enqueued
