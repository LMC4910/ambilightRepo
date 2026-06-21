"""
HDR → SDR tone-mapping for colour analysis (G2)
===============================================
When Windows HDR is enabled, a frame pulled through the (8-bit) capture path
looks **washed out**: flat mid contrast and muted saturation, because HDR
content encoded for a wide container is being interpreted with an SDR transfer
curve. Analysing it as-is yields dull, grey LED colours.

This module applies a cheap, fully-vectorised recovery on the already-downscaled
analysis frame (e.g. 80×45) *before* zone extraction, and only when the source
monitor is HDR (see :mod:`ambilight.hdr`). It is deliberately a no-op at neutral
settings so SDR content — or HDR with recovery disabled — is untouched.

The curve has three independent knobs so it can be tuned once real HDR capture
output is observed on hardware:
  * ``exposure``           — linear gain applied first (tames/raises overall level).
  * ``contrast``           — S-curve strength about mid-grey (restores punch lost
                             to the flat HDR-through-SDR look).
  * ``saturation_recovery``— scales chroma about per-pixel luma (recovers colour).
"""

from __future__ import annotations

import numpy as np

# Rec. 709 luma weights for RGB (used for the saturation pivot).
_LUMA_RGB = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def tonemap_bgr(
    frame: np.ndarray,
    exposure: float = 1.0,
    contrast: float = 1.15,
    saturation_recovery: float = 1.5,
) -> np.ndarray:
    """Recover SDR-looking colour from a washed HDR *frame*.

    Parameters
    ----------
    frame:
        ``(H, W, 3)`` BGR uint8 analysis frame (OpenCV channel order).
    exposure:
        Linear multiplier applied before the contrast curve. ``1.0`` = none.
    contrast:
        S-curve strength about mid-grey. ``1.0`` = none; ``>1`` deepens shadows
        and lifts highlights to counter the flat HDR look.
    saturation_recovery:
        Chroma scale about per-pixel luma. ``1.0`` = none; ``>1`` revives colour.

    Returns
    -------
    numpy.ndarray
        ``(H, W, 3)`` BGR uint8 frame. Returned unchanged (a copy is avoided)
        when all knobs are neutral or the frame is empty.
    """
    if frame is None or frame.size == 0:
        return frame
    if exposure == 1.0 and contrast == 1.0 and saturation_recovery == 1.0:
        return frame

    f = frame.astype(np.float32) / 255.0

    # 1. Exposure (linear gain).
    if exposure != 1.0:
        f *= exposure

    # 2. Contrast S-curve about mid-grey — restores mid-tone punch.
    if contrast != 1.0:
        f = (f - 0.5) * contrast + 0.5

    # 3. Saturation recovery about per-pixel luma. Frame is BGR, so reverse the
    #    luma weights to match channel order.
    if saturation_recovery != 1.0:
        luma = (f * _LUMA_RGB[::-1]).sum(axis=2, keepdims=True)
        f = luma + (f - luma) * saturation_recovery

    np.clip(f, 0.0, 1.0, out=f)
    return (f * 255.0 + 0.5).astype(np.uint8)
