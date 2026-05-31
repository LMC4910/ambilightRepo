"""
Zone Manager Module
===================
Decomposes a captured frame into configurable screen zones and returns the
pixel region for each zone.

Zone Layout
-----------
Zones are defined per screen edge: top, bottom, left, right.  Each edge is
divided into *N* equal-width (or equal-height) segments.  The corners are
shared between two edges and are included in both to avoid dark gaps.

Zone coordinates are stored as (x0, y0, x1, y1) slices into the analysis
resolution frame.

The :class:`ZoneManager` is resolution-aware: when the frame size changes it
recomputes coordinates automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Zone:
    """
    Represents one Ambilight zone.

    Attributes
    ----------
    name:
        Human-readable label, e.g. ``"top_3"``.
    edge:
        Which screen edge: ``"top"``, ``"bottom"``, ``"left"``, ``"right"``.
    index:
        Zero-based zone index along the edge.
    x0, y0, x1, y1:
        Pixel slice coordinates into the analysis-resolution frame
        (exclusive upper bounds, i.e. ``frame[y0:y1, x0:x1]``).
    """

    name: str
    edge: str
    index: int
    x0: int
    y0: int
    x1: int
    y1: int


class ZoneManager:
    """
    Computes and caches :class:`Zone` objects for a given frame size.

    Parameters
    ----------
    n_top:
        Number of zones along the top edge.
    n_bottom:
        Number of zones along the bottom edge.
    n_left:
        Number of zones along the left edge.
    n_right:
        Number of zones along the right edge.
    edge_fraction:
        Fraction of frame height/width that defines the edge strip thickness.
        0.2 means 20% of the frame height for top/bottom edges.
    """

    def __init__(
        self,
        n_top: int = 7,
        n_bottom: int = 7,
        n_left: int = 4,
        n_right: int = 4,
        edge_fraction: float = 0.25,
    ) -> None:
        self.n_top = n_top
        self.n_bottom = n_bottom
        self.n_left = n_left
        self.n_right = n_right
        self.edge_fraction = edge_fraction

        self._frame_width: int = 0
        self._frame_height: int = 0
        self._zones: list[Zone] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_zones(self, frame_width: int, frame_height: int) -> list[Zone]:
        """
        Return the full list of :class:`Zone` objects for the given frame size.

        Results are cached; the list is only recomputed when *frame_width* or
        *frame_height* changes.
        """
        if (frame_width, frame_height) == (self._frame_width, self._frame_height):
            return self._zones

        self._frame_width = frame_width
        self._frame_height = frame_height
        self._zones = self._build_zones(frame_width, frame_height)
        logger.debug(
            "[Zones] Computed %d zones for %dx%d frame.",
            len(self._zones), frame_width, frame_height,
        )
        return self._zones

    def extract_regions(
        self, frame: np.ndarray
    ) -> list[tuple[Zone, np.ndarray]]:
        """
        Slice *frame* into per-zone pixel arrays.

        Parameters
        ----------
        frame:
            (H, W, 3) BGR uint8 array at analysis resolution.

        Returns
        -------
        list of (Zone, ndarray)
            Each entry pairs a :class:`Zone` with its (h, w, 3) pixel region.
        """
        h, w = frame.shape[:2]
        zones = self.compute_zones(w, h)
        return [
            (zone, frame[zone.y0 : zone.y1, zone.x0 : zone.x1])
            for zone in zones
        ]

    @property
    def zones(self) -> list[Zone]:
        """Currently cached zone list (may be empty before first call)."""
        return self._zones

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_zones(self, w: int, h: int) -> list[Zone]:
        zones: list[Zone] = []
        strip_h = max(1, int(h * self.edge_fraction))
        strip_w = max(1, int(w * self.edge_fraction))

        # Top edge — divided horizontally into n_top zones
        for i, (x0, x1) in enumerate(self._divide(w, self.n_top)):
            zones.append(Zone(
                name=f"top_{i}",
                edge="top",
                index=i,
                x0=x0, y0=0,
                x1=x1, y1=strip_h,
            ))

        # Bottom edge
        for i, (x0, x1) in enumerate(self._divide(w, self.n_bottom)):
            zones.append(Zone(
                name=f"bottom_{i}",
                edge="bottom",
                index=i,
                x0=x0, y0=h - strip_h,
                x1=x1, y1=h,
            ))

        # Left edge — divided vertically into n_left zones
        for i, (y0, y1) in enumerate(self._divide(h, self.n_left)):
            zones.append(Zone(
                name=f"left_{i}",
                edge="left",
                index=i,
                x0=0, y0=y0,
                x1=strip_w, y1=y1,
            ))

        # Right edge
        for i, (y0, y1) in enumerate(self._divide(h, self.n_right)):
            zones.append(Zone(
                name=f"right_{i}",
                edge="right",
                index=i,
                x0=w - strip_w, y0=y0,
                x1=w, y1=y1,
            ))

        return zones

    @staticmethod
    def _divide(total: int, n: int) -> list[tuple[int, int]]:
        """Split [0, total) into *n* roughly equal integer slices."""
        if n <= 0:
            return []
        step = total / n
        segments = []
        for i in range(n):
            start = int(round(i * step))
            end = int(round((i + 1) * step))
            segments.append((start, end))
        return segments
