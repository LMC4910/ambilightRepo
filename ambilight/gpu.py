"""
GPU Acceleration Module
=======================
Provides a unified interface for GPU-accelerated array operations used in
colour analysis and frame processing.

Strategy
--------
1. Attempt to import the preferred backend (cupy, opencv_cuda, torch).
2. Verify the backend is actually functional (CUDA context, device count …).
3. Fall back to pure NumPy/CPU if the backend is unavailable or broken.

All public functions accept and return standard ``numpy.ndarray`` objects so
that the rest of the codebase remains backend-agnostic.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class GpuBackend(Enum):
    CUPY = auto()
    OPENCV_CUDA = auto()
    TORCH = auto()
    CPU = auto()


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _probe_cupy() -> bool:
    """Return True if CuPy can allocate a small GPU array."""
    try:
        import cupy as cp  # type: ignore[import-untyped]
        _ = cp.zeros(4, dtype=cp.uint8)
        return True
    except Exception:
        return False


def _probe_opencv_cuda() -> bool:
    """Return True if OpenCV was built with CUDA and at least one GPU exists."""
    try:
        import cv2  # type: ignore[import-untyped]
        return cv2.cuda.getCudaEnabledDeviceCount() > 0
    except Exception:
        return False


def _probe_torch() -> bool:
    """Return True if PyTorch can see at least one CUDA device."""
    try:
        import torch  # type: ignore[import-untyped]
        return torch.cuda.is_available()
    except Exception:
        return False


def detect_backend(prefer: str = "cupy", fallback_to_cpu: bool = True) -> GpuBackend:
    """
    Detect the best available GPU backend.

    Parameters
    ----------
    prefer:
        Preferred backend name: ``"cupy"``, ``"opencv_cuda"``, ``"torch"``,
        or ``"none"`` to skip GPU entirely.
    fallback_to_cpu:
        When *True*, silently return :attr:`GpuBackend.CPU` if no GPU backend
        is available.  When *False*, raise ``RuntimeError``.

    Returns
    -------
    GpuBackend
        The selected backend enum value.
    """
    if prefer == "none":
        logger.info("[GPU] GPU disabled by configuration.")
        return GpuBackend.CPU

    probes: dict[str, tuple[GpuBackend, callable]] = {
        "cupy": (GpuBackend.CUPY, _probe_cupy),
        "opencv_cuda": (GpuBackend.OPENCV_CUDA, _probe_opencv_cuda),
        "torch": (GpuBackend.TORCH, _probe_torch),
    }

    # Try preferred first, then the rest
    order = [prefer] + [k for k in probes if k != prefer]
    for name in order:
        if name not in probes:
            continue
        backend_enum, probe_fn = probes[name]
        try:
            if probe_fn():
                logger.info("[GPU] Using backend: %s", name)
                return backend_enum
        except Exception as exc:
            logger.debug("[GPU] Backend '%s' probe failed: %s", name, exc)

    if fallback_to_cpu:
        logger.warning("[GPU] No GPU backend available; falling back to CPU.")
        return GpuBackend.CPU

    raise RuntimeError(
        "No GPU backend available and fallback_to_cpu=False."
    )


# ---------------------------------------------------------------------------
# Accelerated operations
# ---------------------------------------------------------------------------

class GpuAccelerator:
    """
    Wraps GPU-accelerated (or CPU-fallback) array operations.

    Instances are cheap to create; prefer a single shared instance per
    process.
    """

    def __init__(self, backend: GpuBackend) -> None:
        self.backend = backend
        self._cp: Optional[object] = None      # cupy module
        self._torch: Optional[object] = None   # torch module

        if backend == GpuBackend.CUPY:
            import cupy as cp  # type: ignore[import-untyped]
            self._cp = cp
        elif backend == GpuBackend.TORCH:
            import torch  # type: ignore[import-untyped]
            self._torch = torch

    # ------------------------------------------------------------------
    # Public API – all inputs/outputs are numpy arrays
    # ------------------------------------------------------------------

    def resize(
        self,
        frame: np.ndarray,
        width: int,
        height: int,
    ) -> np.ndarray:
        """
        Resize *frame* (H×W×3 uint8) to (*height*, *width*) using the
        fastest available interpolation.
        """
        if self.backend == GpuBackend.OPENCV_CUDA:
            return self._opencv_cuda_resize(frame, width, height)
        if self.backend == GpuBackend.CUPY and self._cp is not None:
            return self._cupy_resize(frame, width, height)
        if self.backend == GpuBackend.TORCH and self._torch is not None:
            return self._torch_resize(frame, width, height)
        return self._cpu_resize(frame, width, height)

    def mean_color(self, region: np.ndarray) -> np.ndarray:
        """
        Compute the mean RGB colour of *region* (H×W×3 uint8).

        Returns a (3,) uint8 array [R, G, B].
        """
        if self.backend == GpuBackend.CUPY and self._cp is not None:
            cp = self._cp
            gpu = cp.asarray(region)
            mean = cp.mean(gpu.reshape(-1, 3), axis=0)
            return cp.asnumpy(mean).astype(np.uint8)
        return np.mean(region.reshape(-1, 3), axis=0).astype(np.uint8)

    def weighted_mean_color(
        self,
        region: np.ndarray,
        weights: np.ndarray,
    ) -> np.ndarray:
        """
        Weighted mean of pixel colours.

        Parameters
        ----------
        region:
            (N, 3) float32 pixel array.
        weights:
            (N,) float32 weight array (need not sum to 1).

        Returns
        -------
        numpy.ndarray
            (3,) uint8 colour array.
        """
        if self.backend == GpuBackend.CUPY and self._cp is not None:
            cp = self._cp
            g_pixels = cp.asarray(region)
            g_weights = cp.asarray(weights)
            total = cp.sum(g_weights)
            if total == 0:
                return np.zeros(3, dtype=np.uint8)
            result = cp.dot(g_weights, g_pixels) / total
            return cp.asnumpy(result).astype(np.uint8)

        total = weights.sum()
        if total == 0:
            return np.zeros(3, dtype=np.uint8)
        return (np.dot(weights, region) / total).astype(np.uint8)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cpu_resize(frame: np.ndarray, width: int, height: int) -> np.ndarray:
        # Pillow keeps the lean build small (no OpenCV). Channel order is
        # irrelevant to resizing, so BGR frames round-trip correctly. If OpenCV
        # happens to be installed (GPU build) prefer its slightly faster resize.
        try:
            import cv2  # type: ignore[import-untyped]
            return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
        except Exception:
            from PIL import Image
            img = Image.fromarray(frame).resize((width, height), Image.BILINEAR)
            return np.asarray(img)

    @staticmethod
    def _opencv_cuda_resize(
        frame: np.ndarray, width: int, height: int
    ) -> np.ndarray:
        import cv2  # type: ignore[import-untyped]
        gpu_src = cv2.cuda_GpuMat()
        gpu_src.upload(frame)
        gpu_dst = cv2.cuda.resize(gpu_src, (width, height))
        return gpu_dst.download()

    def _cupy_resize(
        self, frame: np.ndarray, width: int, height: int
    ) -> np.ndarray:
        # CuPy doesn't have a direct image resize; delegate to OpenCV which
        # is faster than a round-trip through CuPy for small targets anyway.
        return self._cpu_resize(frame, width, height)

    def _torch_resize(
        self, frame: np.ndarray, width: int, height: int
    ) -> np.ndarray:
        torch = self._torch
        # (H, W, C) -> (1, C, H, W) for torch interpolation
        tensor = torch.from_numpy(frame).permute(2, 0, 1).unsqueeze(0).float()
        resized = torch.nn.functional.interpolate(
            tensor,
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )
        return resized.squeeze(0).permute(1, 2, 0).byte().numpy()
