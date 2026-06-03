"""Tests for the MagicHome command builder + reconnect backoff (FR-DEV-08)."""

from ambilight.led_output import _build_rgb_command, MagicHomeController


def test_rgb_command_framing_and_checksum():
    cmd = _build_rgb_command(10, 20, 30)
    assert len(cmd) == 8
    assert cmd[0] == 0x31
    assert (cmd[1], cmd[2], cmd[3]) == (10, 20, 30)
    assert cmd[-1] == sum(cmd[:-1]) & 0xFF  # checksum is low byte of the sum


def test_rgb_command_masks_out_of_range():
    cmd = _build_rgb_command(300, -5, 256)
    assert cmd[1] == 300 & 0xFF and cmd[3] == 256 & 0xFF


def test_exponential_backoff_growth_and_cap():
    c = MagicHomeController("127.0.0.1", reconnect_interval=1.0, reconnect_backoff_max=30.0)
    c._reconnect_failures = 0
    assert c._current_backoff() == 1.0
    c._reconnect_failures = 3
    assert c._current_backoff() == 8.0       # 1 * 2^3
    c._reconnect_failures = 20
    assert c._current_backoff() == 30.0      # capped


def test_capability_flags():
    c = MagicHomeController("127.0.0.1", kind="addressable", led_count=60)
    assert c.is_addressable and c.led_count == 60
    assert not MagicHomeController("127.0.0.1").is_addressable
