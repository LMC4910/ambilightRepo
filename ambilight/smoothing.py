"""
Smoothing Engine Module
=======================
Implements temporal colour smoothing to eliminate flickering and prevent
jarring colour jumps — the key characteristic that separates premium Ambilight
systems from basic implementations.

Algorithm
---------
**Exponential Moving Average (EMA)** with adaptive alpha:

    smoothed[t] = alpha * raw[t] + (1 - alpha) * smoothed[t-1]

* **Small changes** (colour delta < *fast_threshold*) → low alpha → slow,
  gentle transitions.  Prevents shimmer from scene noise.
* **Large changes** (colour delta >= *fast_threshold*) → high alpha → fast
  response.  Scene cuts, light switches, and dramatic colour shifts are tracked
  immediately.

The adaptive logic computes a per-channel Chebyshev distance between the
new raw colour and the current smoothed colour, then blends between the two
alpha values accordingly.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SmoothedColor:
    """
    Single-channel triple (R, G, B) smoother backed by EMA.

    Maintains internal float state to avoid rounding error accumulation
    across frames.
    """

    def __init__(
        self,
        base_alpha: float = 0.15,
        fast_alpha: float = 0.55,
        fast_threshold: int = 60,
        min_change: int = 2,
    ) -> None:
        """
        Parameters
        ----------
        base_alpha:
            EMA coefficient for slow (small-change) smoothing.
            Range (0, 1]; lower = smoother / more lag.
        fast_alpha:
            EMA coefficient applied when the colour change is large.
        fast_threshold:
            Chebyshev distance (max channel delta) above which *fast_alpha*
            is used exclusively.
        min_change:
            Skip smoothing update if the Chebyshev distance between the new
            raw colour and the current smoothed colour is below this value.
            Prevents pointless network transmissions.
        """
        self._base_alpha = base_alpha
        self._fast_alpha = fast_alpha
        self._fast_threshold = fast_threshold
        self._min_change = min_change

        # Internal float state initialised to "unset"
        self._state: Optional[np.ndarray] = None

    def update(self, raw: tuple[int, int, int]) -> tuple[int, int, int]:
        """
        Apply one EMA step.

        Parameters
        ----------
        raw:
            The latest raw (R, G, B) colour from the analyser.

        Returns
        -------
        tuple[int, int, int]
            The smoothed (R, G, B) colour to send to the LED controller.
        """
        raw_arr = np.array(raw, dtype=np.float32)

        # First frame — skip smoothing
        if self._state is None:
            self._state = raw_arr.copy()
            return raw

        delta = float(np.max(np.abs(raw_arr - self._state)))

        # Dead-zone: suppress update when change is negligible
        if delta < self._min_change:
            return self._to_rgb(self._state)

        # Adaptive alpha — linear interpolation between base and fast
        t = min(1.0, delta / self._fast_threshold)
        alpha = self._base_alpha + t * (self._fast_alpha - self._base_alpha)

        self._state = alpha * raw_arr + (1.0 - alpha) * self._state
        return self._to_rgb(self._state)

    def reset(self, color: Optional[tuple[int, int, int]] = None) -> None:
        """Reset internal state, optionally seeding with *color*."""
        self._state = np.array(color, dtype=np.float32) if color else None

    @staticmethod
    def _to_rgb(arr: np.ndarray) -> tuple[int, int, int]:
        clipped = np.clip(arr, 0, 255).astype(np.uint8)
        return (int(clipped[0]), int(clipped[1]), int(clipped[2]))

    @property
    def current(self) -> Optional[tuple[int, int, int]]:
        """Current smoothed colour, or *None* if not yet initialised."""
        return self._to_rgb(self._state) if self._state is not None else None


class SmoothingEngine:
    """
    Multi-zone smoothing engine.

    Maintains one :class:`SmoothedColor` instance per zone name and one for
    the combined single-output colour.  Zone smoothers are created lazily
    on first use so the caller does not need to know the zone layout upfront.

    Parameters
    ----------
    enabled:
        When *False*, raw colours are passed through unchanged.
    base_alpha:
        Base EMA coefficient for slow transitions.
    fast_alpha:
        EMA coefficient for large/fast transitions.
    fast_threshold:
        Chebyshev distance that triggers fast-alpha mode.
    min_change:
        Dead-zone: skip update if change < this.
    """

    def __init__(
        self,
        enabled: bool = True,
        base_alpha: float = 0.15,
        fast_alpha: float = 0.55,
        fast_threshold: int = 60,
        min_change: int = 2,
    ) -> None:
        self.enabled = enabled
        self._kwargs = dict(
            base_alpha=base_alpha,
            fast_alpha=fast_alpha,
            fast_threshold=fast_threshold,
            min_change=min_change,
        )
        self._smoothers: dict[str, SmoothedColor] = {}
        self._combined_smoother = SmoothedColor(**self._kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def smooth_zones(
        self,
        zone_colors: list[tuple[object, tuple[int, int, int]]],
    ) -> list[tuple[object, tuple[int, int, int]]]:
        """
        Apply per-zone EMA smoothing.

        Parameters
        ----------
        zone_colors:
            List of (Zone, (R, G, B)) pairs from the colour analyser.

        Returns
        -------
        list of (Zone, (R, G, B))
            Smoothed colours for each zone.
        """
        if not self.enabled:
            return zone_colors

        result = []
        for zone, color in zone_colors:
            key: str = getattr(zone, "name", str(zone))
            if key not in self._smoothers:
                self._smoothers[key] = SmoothedColor(**self._kwargs)
            smoothed = self._smoothers[key].update(color)
            result.append((zone, smoothed))
        return result

    def smooth_combined(
        self, color: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        """
        Apply EMA to the single combined output colour.

        Parameters
        ----------
        color:
            Raw combined (R, G, B) from :meth:`ColorAnalyzer.combine_zone_colors`.

        Returns
        -------
        tuple[int, int, int]
            Smoothed colour.
        """
        if not self.enabled:
            return color
        return self._combined_smoother.update(color)

    def reset_all(self) -> None:
        """Reset all smoothers (e.g. after a long pause)."""
        for s in self._smoothers.values():
            s.reset()
        self._combined_smoother.reset()

    @property
    def zone_count(self) -> int:
        """Number of zones currently tracked."""
        return len(self._smoothers)
