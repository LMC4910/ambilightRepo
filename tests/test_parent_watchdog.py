"""Tests for the parent-process watchdog (force-quit service cleanup).

Verifies the deterministic pieces: PID liveness, the env-driven enable/disable
gate, and that the shutdown callback actually fires when a watched process dies.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

from ambilight.parent_watchdog import (
    _pid_alive, start_parent_watchdog, PARENT_PID_ENV,
)


def test_pid_alive_for_self_and_dead_pids():
    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(0) is False
    assert _pid_alive(-1) is False
    assert _pid_alive(0x7FFFFFFF) is False  # implausibly high, not running


def test_no_watchdog_without_env(monkeypatch):
    monkeypatch.delenv(PARENT_PID_ENV, raising=False)
    assert start_parent_watchdog(lambda: None) is None


def test_no_watchdog_for_invalid_or_self_pid(monkeypatch):
    monkeypatch.setenv(PARENT_PID_ENV, "not-a-number")
    assert start_parent_watchdog(lambda: None) is None
    monkeypatch.setenv(PARENT_PID_ENV, str(os.getpid()))
    assert start_parent_watchdog(lambda: None) is None  # watching ourselves = pointless


def test_watchdog_fires_when_parent_exits(monkeypatch):
    # A real short-lived child stands in for the Electron shell.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setenv(PARENT_PID_ENV, str(child.pid))

    fired = threading.Event()
    thread = start_parent_watchdog(fired.set, poll_interval=0.05)
    assert thread is not None
    try:
        assert not fired.wait(0.3)   # parent still alive → callback must NOT fire
        child.terminate()
        child.wait(timeout=5)
        assert fired.wait(2.0)       # parent gone → callback fires promptly
    finally:
        if child.poll() is None:
            child.kill()
