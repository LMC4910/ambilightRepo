"""Tests for the pipeline notification-flash overlay state machine."""

import queue

import pytest

from ambilight import pipeline as pmod
from ambilight.config import AppConfig
from ambilight.pipeline import AmbilightPipeline


class FakeLed:
    def __init__(self, addressable=False, fail=False):
        self._addressable = addressable
        self.fail = fail            # simulate an unreachable device (sends return False)
        self.rgb_calls = []
        self.pixel_calls = []
        self.ensure_on_calls = 0
        self.turn_off_calls = 0

    @property
    def is_addressable(self):
        return self._addressable

    def set_rgb(self, r, g, b):
        self.rgb_calls.append((r, g, b))
        return not self.fail

    def set_pixels(self, pixels):
        self.pixel_calls.append(list(pixels))
        return not self.fail

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
        self.last_output_rgb = (0, 0, 0)


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
    p._channels[0].last_output_rgb = (5, 6, 7)   # per-channel frozen frame
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    # on-segment paints the flash colour
    assert p._service_idle_flash(0.0) is True
    assert led.rgb_calls[-1] == (40, 41, 42)
    # after it ends, the frozen frame is restored (paused path)
    assert p._service_idle_flash(0.20) is False
    assert led.rgb_calls[-1] == (5, 6, 7)


def test_flash_started_active_restores_when_paused_mid_flash():
    # Regression: a flash that begins while active must still restore the frozen
    # frame if the app pauses (screen lock) before it finishes.
    p, led = _pipeline()
    p._power = True
    p._channels[0].last_output_rgb = (5, 6, 7)
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    # Starts in the active path...
    assert p._flash_step(0.0, paused=False) == ("on", (40, 41, 42))
    # ...app pauses; the idle/paused path drives it to completion → restore.
    assert p._service_idle_flash(0.20) is False
    assert led.rgb_calls[-1] == (5, 6, 7)


def test_per_channel_restore_uses_each_channels_color():
    # Multi-device: each strip restores its own prior colour, not a shared one.
    p, led_a = _pipeline()
    led_b = FakeLed()
    p._channels.append(FakeChannel(led_b))
    p._power = True
    p._channels[0].last_output_rgb = (1, 2, 3)
    p._channels[1].last_output_rgb = (9, 8, 7)
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    p._service_idle_flash(0.0)             # on
    p._service_idle_flash(0.20)            # finish → per-channel restore
    assert led_a.rgb_calls[-1] == (1, 2, 3)
    assert led_b.rgb_calls[-1] == (9, 8, 7)


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


def test_queue_keeps_all_bursts():
    # A burst of distinct notifications is queued in full (no coalescing) so each
    # one flashes in turn — the fix for stacked alerts being silently dropped.
    p, _ = _pipeline()
    for _ in range(5):
        _flash(p)
    assert len(p._flash_queue) == 5


def test_queued_flash_gets_leading_gap():
    # The first flash starts immediately; a second flash queued behind it gets a
    # leading dark gap so the two stay visually distinct (vital when they share a
    # colour). Gap duration comes from notifications.inter_flash_gap_ms.
    p, _ = _pipeline()
    p._cfg.notifications.inter_flash_gap_ms = 100
    _flash(p, blink_count=1, on_ms=100, off_ms=0)
    _flash(p, blink_count=1, on_ms=100, off_ms=0)
    first = p._flash_queue[0]["segments"]
    second = p._flash_queue[1]["segments"]
    assert [s["on"] for s in first] == [True]                 # no leading gap
    assert [s["on"] for s in second] == [False, True]         # leading dark gap
    assert second[0]["dur"] == pytest.approx(0.1)


def test_queue_cap_drops_oldest_and_warns():
    p, _ = _pipeline()
    for _ in range(pmod._FLASH_QUEUE_MAX + 5):
        _flash(p)
    assert len(p._flash_queue) == pmod._FLASH_QUEUE_MAX


def test_flash_retries_then_drops_on_persistent_failure():
    # An unreachable device: the flash is retried up to max_retries, then skipped
    # so the queue keeps moving instead of stalling on a dead device.
    p, led = _pipeline()
    led.fail = True
    p._cfg.notifications.flash_max_retries = 3
    p._channels[0].last_output_rgb = (5, 6, 7)
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    t = 0.0
    # Each failed attempt re-queues with a retry back-off; advance time past it.
    for _ in range(3):
        assert p._flash_step(t, paused=False) == ("inactive",)
        t += pmod._FLASH_RETRY_DELAY_S + 0.01
    # After the 3rd attempt the flash is dropped and the queue is empty.
    assert len(p._flash_queue) == 0
    assert p._flash_active is None


def test_flash_recovers_after_transient_failure():
    # First attempt fails, device comes back, second attempt lights the strip.
    p, led = _pipeline()
    led.fail = True
    p._cfg.notifications.flash_max_retries = 3
    _flash(p, color=(40, 41, 42), blink_count=1, on_ms=100, off_ms=0)
    assert p._flash_step(0.0, paused=False) == ("inactive",)   # attempt 1 fails → re-queued
    assert len(p._flash_queue) == 1
    led.fail = False
    # Wait out the retry back-off, then it plays.
    assert p._flash_step(pmod._FLASH_RETRY_DELAY_S + 0.01, paused=False) == ("on", (40, 41, 42))


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
