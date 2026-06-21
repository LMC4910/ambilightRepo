"""Tests for HDR detection + the pipeline's tone-map decision (G2).

The DISPLAYCONFIG ctypes calls need a real display, so these mock the two Win32
helpers and cover the deterministic logic: GDI-name→index mapping, off-Windows
SDR fallback, detector caching, and the auto/on/off tone-map gate.
"""

import numpy as np

import ambilight.hdr as hdr
from ambilight.config import AppConfig
from ambilight.pipeline import AmbilightPipeline


# --- monitor_hdr_states mapping -------------------------------------------

def test_off_windows_reports_sdr(monkeypatch):
    monkeypatch.setattr(hdr.sys, "platform", "linux")
    assert hdr.monitor_hdr_states() == {}


def test_states_map_gdi_name_to_capture_index(monkeypatch):
    monkeypatch.setattr(hdr.sys, "platform", "win32")
    # EnumDisplayMonitors order → capture monitor_index.
    monkeypatch.setattr(hdr, "_gdi_names_by_index",
                        lambda: [r"\\.\DISPLAY1", r"\\.\DISPLAY2"])
    monkeypatch.setattr(hdr, "_hdr_by_gdi_name",
                        lambda: {r"\\.\DISPLAY1": False, r"\\.\DISPLAY2": True})
    assert hdr.monitor_hdr_states() == {0: False, 1: True}


def test_missing_gdi_name_defaults_to_sdr(monkeypatch):
    monkeypatch.setattr(hdr.sys, "platform", "win32")
    monkeypatch.setattr(hdr, "_gdi_names_by_index", lambda: [r"\\.\DISPLAY1"])
    monkeypatch.setattr(hdr, "_hdr_by_gdi_name", lambda: {})  # no info for it
    assert hdr.monitor_hdr_states() == {0: False}


def test_query_failure_falls_back_to_empty(monkeypatch):
    monkeypatch.setattr(hdr.sys, "platform", "win32")
    def _boom():
        raise OSError("ctypes blew up")
    monkeypatch.setattr(hdr, "_gdi_names_by_index", _boom)
    assert hdr.monitor_hdr_states() == {}


# --- HdrDetector ----------------------------------------------------------

def test_detector_caches_and_reports(monkeypatch):
    monkeypatch.setattr(hdr, "monitor_hdr_states", lambda: {0: True, 1: False})
    d = hdr.HdrDetector()
    assert d.is_hdr(0) is True
    assert d.is_hdr(1) is False
    assert d.is_hdr(5) is False  # unknown index → SDR


def test_detector_refresh_picks_up_changes(monkeypatch):
    state = {"v": {0: False}}
    monkeypatch.setattr(hdr, "monitor_hdr_states", lambda: state["v"])
    d = hdr.HdrDetector()
    assert d.is_hdr(0) is False
    state["v"] = {0: True}
    d.refresh()
    assert d.is_hdr(0) is True


# --- pipeline tone-map gate (auto | on | off) -----------------------------

class _FakeHdr:
    def __init__(self, hdr_on): self._on = hdr_on
    def is_hdr(self, mi): return self._on


def _pipeline_with(mode, hdr_on):
    cfg = AppConfig()
    cfg.capture.hdr.mode = mode
    p = AmbilightPipeline(config=cfg)
    p._hdr = _FakeHdr(hdr_on)
    return p


def test_auto_tonemaps_only_when_hdr_detected():
    assert _pipeline_with("auto", hdr_on=True)._should_tonemap(0) is True
    assert _pipeline_with("auto", hdr_on=False)._should_tonemap(0) is False


def test_on_always_tonemaps_off_never():
    assert _pipeline_with("on", hdr_on=False)._should_tonemap(0) is True
    assert _pipeline_with("off", hdr_on=True)._should_tonemap(0) is False
