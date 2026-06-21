"""Tests for the LedDriver abstraction + factory (A0).

The factory selects a concrete driver from a spec's ``protocol`` field, and the
ABC must not be instantiable. MagicHome behavior is covered by
test_led_output.py (unchanged via the re-export shim)."""

import pytest

from ambilight.devices import LedDriver, create_driver
from ambilight.devices.magichome import MagicHomeController
from ambilight.led_output import MagicHomeController as ShimMagicHome


def test_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LedDriver()


def test_magichome_subclasses_leddriver():
    assert issubclass(MagicHomeController, LedDriver)


def test_shim_reexports_same_class():
    # Existing `from ambilight.led_output import MagicHomeController` must keep working.
    assert ShimMagicHome is MagicHomeController


def test_factory_builds_magichome():
    d = create_driver({"protocol": "magichome", "ip": "1.2.3.4", "port": 5577,
                        "kind": "addressable", "led_count": 60})
    assert isinstance(d, MagicHomeController)
    assert d.ip == "1.2.3.4" and d.is_addressable is True and d.led_count == 60


def test_factory_defaults_to_magichome_when_protocol_missing():
    d = create_driver({"ip": "1.2.3.4"})
    assert isinstance(d, MagicHomeController)


def test_factory_unknown_protocol_falls_back_to_magichome(caplog):
    d = create_driver({"protocol": "nonsense", "ip": "1.2.3.4"})
    assert isinstance(d, MagicHomeController)
    assert any("Unknown protocol" in r.message for r in caplog.records)


def test_factory_builds_wled():
    pytest.importorskip("ambilight.devices.wled")
    from ambilight.devices.wled import WledDriver
    d = create_driver({"protocol": "wled", "ip": "1.2.3.4", "led_count": 120})
    assert isinstance(d, WledDriver)
    assert d.is_addressable is True
