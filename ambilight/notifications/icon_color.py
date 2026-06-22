"""
Icon → dominant colour
=======================
Turns an app icon (raw image bytes) into a single vivid RGB colour for the
notification flash, reusing the production :class:`ColorAnalyzer` so we don't
duplicate colour maths.

The icon is decoded with Pillow, composited over black (to drop transparent
halos that would otherwise pull the average toward grey), downscaled, and handed
to ``ColorAnalyzer(mode="dominant")`` which expects a **BGR** uint8 array.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional, Tuple

import numpy as np

from ..color import ColorAnalyzer

logger = logging.getLogger(__name__)

# A single reusable analyzer — "dominant" matches the design intent (the app
# logo's primary colour) and is cheap on a tiny icon.
_analyzer = ColorAnalyzer(mode="dominant")


def _ensure_visible(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Lift near-black / very dim icon colours so the flash is actually visible."""
    r, g, b = rgb
    peak = max(r, g, b)
    if peak == 0:
        return (255, 255, 255)
    if peak < 80:
        # Scale up to a minimum brightness, preserving hue.
        scale = 80.0 / peak
        return (min(255, int(r * scale)), min(255, int(g * scale)), min(255, int(b * scale)))
    return (int(r), int(g), int(b))


def icon_dominant_color(
    icon_bytes: Optional[bytes],
    analyzer: Optional[ColorAnalyzer] = None,
) -> Optional[Tuple[int, int, int]]:
    """Return the dominant ``(r, g, b)`` of an icon, or ``None`` if undetectable.

    ``None`` covers a missing/empty/fully-transparent icon, signalling the caller
    to fall back to a keyword rule or the configured default colour.
    """
    if not icon_bytes:
        return None
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - Pillow is a core dep
        logger.debug("[Notify] Pillow unavailable for icon colour: %s", exc)
        return None

    try:
        img = Image.open(BytesIO(icon_bytes)).convert("RGBA")
        # Composite over black so transparent regions don't skew the colour.
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
        img = img.resize((32, 32))
        rgb = np.asarray(img, dtype=np.uint8)          # H×W×3 RGB
        if rgb.size == 0:
            return None
        # Fully (near-)transparent icons composite to all-black → no usable colour.
        if int(rgb.max()) < 8:
            return None
        bgr = rgb[:, :, ::-1]                           # RGB → BGR for ColorAnalyzer
        result = (analyzer or _analyzer).analyze(bgr)
        return _ensure_visible(result)
    except Exception as exc:
        logger.debug("[Notify] icon colour extraction failed: %s", exc)
        return None
