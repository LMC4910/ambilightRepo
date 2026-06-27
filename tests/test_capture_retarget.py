"""Tests for the game-capture re-inject endpoint (/api/capture/retarget) and the
hook status fields surfaced to the dashboard."""

import asyncio

import ambilight.api_server as api


def test_retarget_sets_hook_and_recaptures(monkeypatch):
    captured = {}
    monkeypatch.setattr(api.ConfigManager, "update",
                        classmethod(lambda cls, ov: captured.__setitem__("override", ov)))
    monkeypatch.setattr(api.ConfigManager, "get", classmethod(lambda cls: object()))

    async def _noop_publish(*a, **k):
        captured["published"] = True
    monkeypatch.setattr(api.bus, "publish", _noop_publish)
    monkeypatch.setattr(api.controller, "recapture",
                        lambda: captured.__setitem__("recaptured", True))

    out = asyncio.run(api.capture_retarget(api.RetargetRequest(target="Witcher3.exe")))

    assert captured["override"] == {"capture": {"hook_target": "Witcher3.exe", "method": "hook"}}
    assert captured.get("recaptured") is True
    assert captured.get("published") is True
    assert out["target"] == "Witcher3.exe"


def test_retarget_blank_target_is_auto(monkeypatch):
    captured = {}
    monkeypatch.setattr(api.ConfigManager, "update",
                        classmethod(lambda cls, ov: captured.__setitem__("override", ov)))
    monkeypatch.setattr(api.ConfigManager, "get", classmethod(lambda cls: object()))

    async def _noop_publish(*a, **k):
        pass
    monkeypatch.setattr(api.bus, "publish", _noop_publish)
    monkeypatch.setattr(api.controller, "recapture", lambda: None)

    out = asyncio.run(api.capture_retarget(api.RetargetRequest(target="   ")))
    assert captured["override"] == {"capture": {"hook_target": "", "method": "hook"}}
    assert out["target"] == "auto"
