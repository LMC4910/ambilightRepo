"""Tests for the honest /health assessment.

"Service alive" must not be reported as healthy when the LEDs aren't actually
being driven — capture producing no frames, or no controller connected. These
cover the degraded-vs-ok decision in ``api_server._health_assessment``.
"""

import ambilight.api_server as api


def _set_status(monkeypatch, running=True, paused=False, restarts=0, pid=123):
    monkeypatch.setattr(
        api.controller, "status",
        lambda: {"running": running, "paused": paused, "restarts": restarts, "pid": pid},
    )


def _set_metrics(monkeypatch, **metrics):
    monkeypatch.setattr(api, "latest_metrics", metrics)


def test_healthy_when_syncing(monkeypatch):
    _set_status(monkeypatch, running=True)
    _set_metrics(monkeypatch, power=True, mode="screen_sync",
                 devices_connected=1, capture_ok=True, capture_backend="wgc", fps=29.0)
    h = api._health_assessment()
    assert h["status"] == "ok"
    assert h["degraded_reasons"] == []


def test_degraded_when_capture_dead(monkeypatch):
    _set_status(monkeypatch, running=True)
    _set_metrics(monkeypatch, power=True, mode="screen_sync",
                 devices_connected=1, capture_ok=False, capture_backend="mss")
    h = api._health_assessment()
    assert h["status"] == "degraded"
    assert "capture_unavailable" in h["degraded_reasons"]


def test_degraded_when_no_device_connected(monkeypatch):
    _set_status(monkeypatch, running=True)
    _set_metrics(monkeypatch, power=True, mode="screen_sync",
                 devices_connected=0, capture_ok=True)
    h = api._health_assessment()
    assert h["status"] == "degraded"
    assert "no_device_connected" in h["degraded_reasons"]


def test_powered_off_is_not_degraded(monkeypatch):
    _set_status(monkeypatch, running=True)
    _set_metrics(monkeypatch, power=False, mode="off",
                 devices_connected=0, capture_ok=True)
    h = api._health_assessment()
    assert h["status"] == "ok"


def test_paused_is_not_degraded(monkeypatch):
    _set_status(monkeypatch, running=True, paused=True)
    _set_metrics(monkeypatch, power=True, mode="screen_sync",
                 devices_connected=0, capture_ok=False)
    h = api._health_assessment()
    assert h["status"] == "ok"


def test_not_running_is_degraded(monkeypatch):
    _set_status(monkeypatch, running=False)
    _set_metrics(monkeypatch)
    h = api._health_assessment()
    assert h["status"] == "degraded"
    assert "pipeline_not_running" in h["degraded_reasons"]
    assert h["pipeline_alive"] is False
