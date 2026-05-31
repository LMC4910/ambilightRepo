"""
Color Analysis Module
=====================
Implements five colour-extraction strategies that operate on a pixel region
(NumPy array) and return a single (R, G, B) uint8 tuple.

Strategies
----------
average
    Simple arithmetic mean of all pixel colours.  Fastest, but washes out
    vibrant content with bright/dark surroundings.

edges
    Average of the four edge strips of the region.  Gives weight to content
    near the screen perimeter — good for wide movie bars.

dominant
    Computes a colour histogram and returns the bin with highest count.
    Handles multi-coloured scenes well without KMeans overhead.

kmeans
    K-Means clustering of pixel colours.  Returns the centroid of the largest
    cluster.  Most accurate, highest CPU cost.

saturation_weighted
    Converts pixels to HSV, discards near-black and near-white pixels, then
    computes a weighted mean where the weight is ``saturation^power``.
    Produces vivid, premium-Ambilight-quality colours.  **Default.**

All strategies accept the same signature so they can be swapped at runtime.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colour mode enum
# ---------------------------------------------------------------------------

class ColorMode(str, Enum):
    AVERAGE = "average"
    EDGES = "edges"
    DOMINANT = "dominant"
    KMEANS = "kmeans"
    SATURATION_WEIGHTED = "saturation_weighted"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_rgb_float(region: np.ndarray) -> np.ndarray:
    """
    Flatten *region* (H×W×3 BGR uint8) to (N, 3) float32 **RGB** array.
    OpenCV frames are BGR; we swap channels here so all downstream code
    works in RGB.
    """
    flat = region.reshape(-1, 3).astype(np.float32)
    # BGR → RGB swap
    flat[:, [0, 2]] = flat[:, [2, 0]]
    return flat


def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """
    Convert (N, 3) float32 RGB array (0-255) to HSV (H 0-360, S 0-1, V 0-1).
    Pure NumPy — no OpenCV dependency inside the hot path.
    """
    r, g, b = rgb[:, 0] / 255.0, rgb[:, 1] / 255.0, rgb[:, 2] / 255.0
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    # Hue
    h = np.zeros(len(r), dtype=np.float32)
    mask_r = (cmax == r) & (delta > 0)
    mask_g = (cmax == g) & (delta > 0)
    mask_b = (cmax == b) & (delta > 0)
    h[mask_r] = 60.0 * (((g[mask_r] - b[mask_r]) / delta[mask_r]) % 6)
    h[mask_g] = 60.0 * (((b[mask_g] - r[mask_g]) / delta[mask_g]) + 2)
    h[mask_b] = 60.0 * (((r[mask_b] - g[mask_b]) / delta[mask_b]) + 4)

    # Saturation
    s = np.where(cmax > 0, delta / cmax, 0.0).astype(np.float32)

    # Value
    v = cmax.astype(np.float32)

    return np.stack([h, s, v], axis=1)


def _filter_extremes(
    pixels: np.ndarray,
    black_threshold: int,
    white_threshold: int,
) -> np.ndarray:
    """
    Remove near-black and near-white pixels.

    Parameters
    ----------
    pixels:
        (N, 3) float32 RGB array.
    black_threshold:
        Pixels where all channels < *black_threshold* are dropped.
    white_threshold:
        Pixels where all channels > *white_threshold* are dropped.

    Returns
    -------
    numpy.ndarray
        Filtered pixel array; may be empty.
    """
    max_ch = pixels.max(axis=1)
    min_ch = pixels.min(axis=1)
    mask = (max_ch >= black_threshold) & (min_ch <= white_threshold)
    return pixels[mask]


# ---------------------------------------------------------------------------
# Analysis strategies
# ---------------------------------------------------------------------------

def analyze_average(
    region: np.ndarray,
    black_threshold: int = 30,
    white_threshold: int = 225,
    **_kwargs: object,
) -> tuple[int, int, int]:
    """
    Arithmetic mean of all pixel colours.

    Parameters
    ----------
    region:
        (H, W, 3) BGR uint8 frame region.

    Returns
    -------
    tuple[int, int, int]
        (R, G, B) 0-255.
    """
    pixels = _to_rgb_float(region)
    if len(pixels) == 0:
        return (0, 0, 0)
    mean = pixels.mean(axis=0)
    return (int(mean[0]), int(mean[1]), int(mean[2]))


def analyze_edges(
    region: np.ndarray,
    black_threshold: int = 30,
    white_threshold: int = 225,
    edge_fraction: float = 0.25,
    **_kwargs: object,
) -> tuple[int, int, int]:
    """
    Average colour of the four edge strips of *region*.

    The edge_fraction controls how thick each strip is relative to the region.
    """
    h, w = region.shape[:2]
    eh = max(1, int(h * edge_fraction))
    ew = max(1, int(w * edge_fraction))

    strips = [
        region[:eh, :],           # top
        region[h - eh:, :],       # bottom
        region[:, :ew],            # left
        region[:, w - ew:],        # right
    ]
    combined = np.concatenate([s.reshape(-1, 3) for s in strips], axis=0)
    pixels = _to_rgb_float(combined.reshape(-1, 3).reshape(-1, 1, 3).squeeze(1))
    pixels = _filter_extremes(pixels, black_threshold, white_threshold)
    if len(pixels) == 0:
        return analyze_average(region)
    mean = pixels.mean(axis=0)
    return (int(mean[0]), int(mean[1]), int(mean[2]))


def analyze_dominant(
    region: np.ndarray,
    black_threshold: int = 30,
    white_threshold: int = 225,
    bins: int = 16,
    **_kwargs: object,
) -> tuple[int, int, int]:
    """
    Return the most common colour using a 3D RGB histogram.

    Parameters
    ----------
    bins:
        Number of histogram bins per channel.  Lower = faster but coarser.
    """
    pixels = _to_rgb_float(region)
    pixels = _filter_extremes(pixels, black_threshold, white_threshold)
    if len(pixels) == 0:
        return analyze_average(region)

    # Discretise
    quantised = (pixels / (256.0 / bins)).astype(np.int32)
    quantised = np.clip(quantised, 0, bins - 1)

    # 3D histogram flattened to 1D using a combined index
    idx = quantised[:, 0] * bins * bins + quantised[:, 1] * bins + quantised[:, 2]
    counts = np.bincount(idx, minlength=bins ** 3)
    best_idx = int(np.argmax(counts))

    b_r = best_idx // (bins * bins)
    b_g = (best_idx % (bins * bins)) // bins
    b_b = best_idx % bins

    scale = 256.0 / bins
    r = min(255, int((b_r + 0.5) * scale))
    g = min(255, int((b_g + 0.5) * scale))
    b = min(255, int((b_b + 0.5) * scale))
    return (r, g, b)


def analyze_kmeans(
    region: np.ndarray,
    black_threshold: int = 30,
    white_threshold: int = 225,
    k: int = 3,
    max_iter: int = 20,
    **_kwargs: object,
) -> tuple[int, int, int]:
    """
    K-Means colour clustering — returns the centroid of the largest cluster.

    A pure-NumPy mini-batch K-Means is used to avoid a SciPy dependency on
    the hot path.  For small analysis frames (80×45) this is fast enough.

    Parameters
    ----------
    k:
        Number of clusters.
    max_iter:
        Maximum Lloyd's iterations.
    """
    pixels = _to_rgb_float(region)
    pixels = _filter_extremes(pixels, black_threshold, white_threshold)
    if len(pixels) < k:
        return analyze_average(region)

    # Subsample for speed — max 1000 pixels
    if len(pixels) > 1000:
        indices = np.random.choice(len(pixels), 1000, replace=False)
        sample = pixels[indices]
    else:
        sample = pixels

    # Initialise centroids with K-Means++ style spread
    rng = np.random.default_rng(seed=42)
    centroids = _kmeans_plusplus_init(sample, k, rng)

    for _ in range(max_iter):
        # Assignment step
        diffs = sample[:, np.newaxis, :] - centroids[np.newaxis, :, :]
        distances = np.sum(diffs ** 2, axis=2)
        labels = np.argmin(distances, axis=1)

        # Update step
        new_centroids = np.array([
            sample[labels == j].mean(axis=0) if np.any(labels == j) else centroids[j]
            for j in range(k)
        ])

        if np.allclose(new_centroids, centroids, atol=1.0):
            break
        centroids = new_centroids

    # Find the largest cluster
    counts = np.array([np.sum(labels == j) for j in range(k)])
    best = int(np.argmax(counts))
    c = centroids[best]
    return (int(c[0]), int(c[1]), int(c[2]))


def _kmeans_plusplus_init(
    data: np.ndarray,
    k: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """K-Means++ initialisation — spread centroids to reduce bad convergence."""
    n = len(data)
    first = rng.integers(0, n)
    centroids = [data[first]]

    for _ in range(1, k):
        dists = np.array([
            min(np.sum((p - c) ** 2) for c in centroids)
            for p in data
        ])
        total = dists.sum()
        if total == 0:
            # All points coincide — pick uniformly
            idx = rng.integers(0, n)
        else:
            probs = dists / total
            idx = rng.choice(n, p=probs)
        centroids.append(data[idx])

    return np.array(centroids, dtype=np.float32)


def analyze_saturation_weighted(
    region: np.ndarray,
    black_threshold: int = 30,
    white_threshold: int = 225,
    power: float = 2.0,
    min_saturation: float = 0.05,
    **_kwargs: object,
) -> tuple[int, int, int]:
    """
    Saturation-weighted mean — the flagship analysis mode.

    Pixels are filtered for extreme brightness, then converted to HSV.
    Each pixel contributes to the final colour proportional to
    ``saturation^power``.  This naturally suppresses grey/white content and
    amplifies vivid colours, mimicking Philips Ambilight's perceptual feel.

    Parameters
    ----------
    power:
        Exponent applied to saturation.  Higher values make the output more
        selective toward highly saturated pixels.
    min_saturation:
        Pixels with saturation below this value are discarded entirely.
    """
    pixels = _to_rgb_float(region)
    pixels = _filter_extremes(pixels, black_threshold, white_threshold)
    if len(pixels) == 0:
        return analyze_average(region)

    hsv = _rgb_to_hsv(pixels)
    saturation = hsv[:, 1]

    # Discard unsaturated pixels
    mask = saturation >= min_saturation
    if mask.sum() < 5:
        # Fall back to simple average if nothing saturated found
        return analyze_average(region)

    pixels = pixels[mask]
    saturation = saturation[mask]

    weights = saturation ** power
    total_weight = weights.sum()
    if total_weight == 0:
        return analyze_average(region)

    weighted_color = (weights[:, np.newaxis] * pixels).sum(axis=0) / total_weight
    r = int(np.clip(weighted_color[0], 0, 255))
    g = int(np.clip(weighted_color[1], 0, 255))
    b = int(np.clip(weighted_color[2], 0, 255))
    return (r, g, b)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_STRATEGY_MAP: dict[str, Callable] = {
    ColorMode.AVERAGE: analyze_average,
    ColorMode.EDGES: analyze_edges,
    ColorMode.DOMINANT: analyze_dominant,
    ColorMode.KMEANS: analyze_kmeans,
    ColorMode.SATURATION_WEIGHTED: analyze_saturation_weighted,
}


class ColorAnalyzer:
    """
    Unified colour analyser that dispatches to the configured strategy.

    Parameters
    ----------
    mode:
        One of the :class:`ColorMode` values (or their string equivalents).
    black_threshold:
        Pixels with all channels below this are treated as black and ignored.
    white_threshold:
        Pixels with all channels above this are treated as white and ignored.
    kmeans_clusters:
        Number of clusters for the ``kmeans`` mode.
    saturation_weight_power:
        Exponent for the ``saturation_weighted`` mode.
    min_saturation:
        Minimum saturation for the ``saturation_weighted`` mode.
    """

    def __init__(
        self,
        mode: str = ColorMode.SATURATION_WEIGHTED,
        black_threshold: int = 30,
        white_threshold: int = 225,
        kmeans_clusters: int = 3,
        saturation_weight_power: float = 2.0,
        min_saturation: float = 0.05,
    ) -> None:
        self.mode = mode
        self._kwargs = dict(
            black_threshold=black_threshold,
            white_threshold=white_threshold,
            k=kmeans_clusters,
            power=saturation_weight_power,
            min_saturation=min_saturation,
        )
        if mode not in _STRATEGY_MAP:
            raise ValueError(
                f"Unknown color mode '{mode}'.  "
                f"Valid modes: {list(_STRATEGY_MAP.keys())}"
            )
        self._fn = _STRATEGY_MAP[mode]
        logger.info("[ColorAnalyzer] Mode: %s", mode)

    def analyze(self, region: np.ndarray) -> tuple[int, int, int]:
        """
        Analyse *region* and return (R, G, B).

        Parameters
        ----------
        region:
            (H, W, 3) BGR uint8 numpy array.

        Returns
        -------
        tuple[int, int, int]
            Colour as (R, G, B) with values 0-255.
        """
        if region.size == 0:
            return (0, 0, 0)
        return self._fn(region, **self._kwargs)

    def analyze_zones(
        self,
        zone_regions: list[tuple["Zone", np.ndarray]],  # noqa: F821
    ) -> list[tuple["Zone", tuple[int, int, int]]]:  # noqa: F821
        """
        Analyse a list of (Zone, pixel_region) pairs.

        Returns
        -------
        list of (Zone, (R, G, B))
        """
        return [(zone, self.analyze(region)) for zone, region in zone_regions]

    def combine_zone_colors(
        self,
        zone_colors: list[tuple[object, tuple[int, int, int]]],
    ) -> tuple[int, int, int]:
        """
        Intelligently combine multiple zone colours into a single ambient colour.

        When the LED hardware only supports a single RGB output, this produces
        the best representative ambient colour by using a saturation-weighted
        mean across all zone colours.

        Parameters
        ----------
        zone_colors:
            List of (zone, (R, G, B)) pairs.

        Returns
        -------
        tuple[int, int, int]
            Combined (R, G, B).
        """
        if not zone_colors:
            return (0, 0, 0)

        colors = np.array([c for _, c in zone_colors], dtype=np.float32)
        # Weight by saturation so vivid zones dominate
        hsv = _rgb_to_hsv(colors)
        weights = hsv[:, 1] ** 2 + 0.01   # small constant avoids all-zero weights
        total = weights.sum()
        weighted = (weights[:, np.newaxis] * colors).sum(axis=0) / total
        return (
            int(np.clip(weighted[0], 0, 255)),
            int(np.clip(weighted[1], 0, 255)),
            int(np.clip(weighted[2], 0, 255)),
        )
