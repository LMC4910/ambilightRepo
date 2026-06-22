"""Tests for icon → dominant colour extraction (Notification Flash)."""

from io import BytesIO

import pytest

from ambilight.notifications.icon_color import icon_dominant_color

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _png(color, size=(32, 32), mode="RGB"):
    img = Image.new(mode, size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_solid_colour_returns_that_colour():
    r, g, b = icon_dominant_color(_png((200, 20, 20)))
    assert r > 150 and g < 80 and b < 80


def test_transparent_icon_returns_none():
    # Fully transparent → composites to black → no usable colour.
    data = _png((0, 0, 0, 0), mode="RGBA")
    assert icon_dominant_color(data) is None


def test_translucent_blob_picks_the_blob_colour():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            img.putpixel((x, y), (30, 60, 220, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    res = icon_dominant_color(buf.getvalue())
    assert res is not None
    r, g, b = res
    assert b > r and b > g     # dominated by the blue blob


def test_none_and_empty_bytes_return_none():
    assert icon_dominant_color(None) is None
    assert icon_dominant_color(b"") is None


def test_tiny_icon_handled():
    assert icon_dominant_color(_png((10, 200, 10), size=(1, 1))) is not None


def test_dark_icon_is_lifted_to_visible():
    # A near-black but non-zero icon should still flash visibly (peak lifted).
    res = icon_dominant_color(_png((10, 0, 0)))
    assert res is not None
    assert max(res) >= 80
