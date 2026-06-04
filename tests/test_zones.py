"""Tests for zone layout (FR-UI-06 / FR-CLR-07): counts, ordering, thickness."""

from ambilight.zones import ZoneManager
from ambilight.config import AppConfig


def test_zone_counts_and_edge_ordering():
    zm = ZoneManager(n_top=5, n_bottom=6, n_left=3, n_right=4)
    zones = zm.compute_zones(80, 45)
    assert len(zones) == 5 + 6 + 3 + 4

    edges = [z.edge for z in zones]
    assert edges[:5] == ["top"] * 5
    assert edges[5:11] == ["bottom"] * 6
    assert edges[11:14] == ["left"] * 3
    assert edges[14:] == ["right"] * 4

    # Per-edge indices are 0-based and in order.
    top = [z for z in zones if z.edge == "top"]
    assert [z.index for z in top] == [0, 1, 2, 3, 4]


def test_divide_covers_full_extent_without_gaps():
    segs = ZoneManager._divide(80, 4)
    assert segs[0][0] == 0 and segs[-1][1] == 80
    for (_, end), (start, _) in zip(segs, segs[1:]):
        assert end == start          # contiguous, no gaps/overlap
    assert ZoneManager._divide(80, 0) == []


def test_edge_fraction_controls_strip_thickness():
    thin = ZoneManager(edge_fraction=0.1).compute_zones(100, 100)
    thick = ZoneManager(edge_fraction=0.5).compute_zones(100, 100)
    thin_top = next(z for z in thin if z.edge == "top")
    thick_top = next(z for z in thick if z.edge == "top")
    assert thick_top.y1 > thin_top.y1     # larger fraction → thicker strip
    assert thin_top.y1 == 10 and thick_top.y1 == 50


def test_config_default_edge_fraction():
    assert AppConfig().zones.edge_fraction == 0.25
