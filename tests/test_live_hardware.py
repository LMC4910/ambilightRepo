"""Live hardware integration tests — real display + real GPU.

These cover the gaps the headless suite cannot:
  * ``test_capture.py`` only exercises backend *selection* with fake backends;
    it never opens dxcam/WGC/MSS or grabs a real frame.
  * there is no ``test_gpu.py`` at all — the entire CuPy path is untested.

This module opens the actual WGC / DXGI(dxcam) / MSS backends against the
running machine's primary monitor and drives the CuPy ``GpuAccelerator`` on the
real CUDA device, asserting both *functionality* (a frame is delivered, the GPU
allocates) and *correctness* (GPU maths match the CPU reference).

OPT-IN — skipped unless ``AMBILIGHT_HW_TESTS=1`` so the default headless
``pytest`` run (and CI) stays green:

    PowerShell:  $env:AMBILIGHT_HW_TESTS=1; pytest tests/test_live_hardware.py -v -s
    bash:        AMBILIGHT_HW_TESTS=1 pytest tests/test_live_hardware.py -v -s

Captured sample frames are written to ``dist/hwtest/`` so you can *see* that
real screen content (e.g. OTT video) was captured — open them after the run.

IMPORTANT interpretation note: a "black" capture is NOT necessarily a failure.
Hardware-DRM OTT video (Netflix app, PlayReady fullscreen) is excluded by
Windows at the compositor and reads black under EVERY backend by design. To
validate that *colour actually flows*, play NON-DRM video (YouTube, windowed
playback) on the primary monitor. The non-black checks below therefore only
*warn* (print) rather than hard-fail, except where a black frame would mean the
backend itself is broken.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AMBILIGHT_HW_TESTS") != "1",
    reason="live hardware test — set AMBILIGHT_HW_TESTS=1 to run",
)

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "dist" / "hwtest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save(name: str, bgr: np.ndarray, max_width: int = 640) -> None:
    """Write a BGR frame to dist/hwtest/<name> as a (downscaled) RGB PNG."""
    try:
        from PIL import Image
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        rgb = np.ascontiguousarray(bgr[..., ::-1])  # BGR -> RGB
        img = Image.fromarray(rgb)
        if img.width > max_width:
            h = int(img.height * max_width / img.width)
            img = img.resize((max_width, h), Image.BILINEAR)
        img.save(ARTIFACT_DIR / name)
        print(f"        saved artifact: {ARTIFACT_DIR / name}")
    except Exception as exc:  # pragma: no cover - artifact is best-effort
        print(f"        (could not save {name}: {exc})")


def _grab_until(backend, tries: int = 80, delay: float = 0.05):
    """Poll ``backend.grab()`` until it returns a frame (backends warm up async)."""
    frame = None
    for _ in range(tries):
        frame = backend.grab()
        if frame is not None:
            return frame
        time.sleep(delay)
    return frame


def _report(tag: str, frame: np.ndarray) -> float:
    from ambilight.capture import is_black_frame
    luma = float(frame.mean())
    black = is_black_frame(frame)
    print(f"        [{tag}] shape={frame.shape} dtype={frame.dtype} "
          f"luma={luma:.1f} black={black}")
    if black:
        print(f"        [{tag}] NOTE: frame is black — expected for hardware-DRM "
              f"OTT content; play NON-DRM video to see colour.")
    return luma


def _dxcam_cleanup() -> None:
    """Reset dxcam's process-global camera registry so later tests can recreate."""
    try:
        import dxcam
        dxcam.clean_up()
    except Exception:
        pass


# ===========================================================================
# GPU / CuPy path  (no display required)
# ===========================================================================

def test_cupy_probe_allocates_on_gpu():
    from ambilight.gpu import _probe_cupy
    assert _probe_cupy() is True, "CuPy could not allocate on the CUDA device"


def test_detect_backend_selects_cupy():
    from ambilight.gpu import detect_backend, GpuBackend
    assert detect_backend("cupy", fallback_to_cpu=True) == GpuBackend.CUPY


def test_cupy_device_info():
    """Informational — print the CUDA device CuPy actually bound to."""
    import cupy as cp
    dev = cp.cuda.Device(0)
    props = cp.cuda.runtime.getDeviceProperties(0)
    name = props["name"].decode() if isinstance(props["name"], bytes) else props["name"]
    free, total = dev.mem_info
    print(f"        [CuPy] device='{name}' "
          f"mem_free={free/1e6:.0f}MB/{total/1e6:.0f}MB "
          f"runtime={cp.cuda.runtime.runtimeGetVersion()}")
    assert total > 0


def test_gpu_resize_shape_and_dtype():
    from ambilight.gpu import GpuAccelerator, GpuBackend
    acc = GpuAccelerator(GpuBackend.CUPY)
    frame = (np.random.rand(216, 384, 3) * 255).astype(np.uint8)
    out = acc.resize(frame, 80, 45)
    assert out.shape == (45, 80, 3)
    assert out.dtype == np.uint8


def test_gpu_mean_color_matches_cpu():
    from ambilight.gpu import GpuAccelerator, GpuBackend
    acc = GpuAccelerator(GpuBackend.CUPY)
    region = (np.random.rand(96, 96, 3) * 255).astype(np.uint8)
    gpu = acc.mean_color(region).astype(int)
    cpu = np.mean(region.reshape(-1, 3), axis=0).astype(np.uint8).astype(int)
    diff = np.abs(gpu - cpu)
    print(f"        [GPU mean_color] gpu={gpu.tolist()} cpu={cpu.tolist()} "
          f"max_diff={int(diff.max())}")
    assert np.all(diff <= 1), f"GPU mean diverges from CPU: {gpu} vs {cpu}"


def test_gpu_weighted_mean_matches_cpu():
    from ambilight.gpu import GpuAccelerator, GpuBackend
    acc = GpuAccelerator(GpuBackend.CUPY)
    region = (np.random.rand(2000, 3) * 255).astype(np.float32)
    weights = np.random.rand(2000).astype(np.float32)
    gpu = acc.weighted_mean_color(region, weights).astype(int)
    total = weights.sum()
    cpu = (np.dot(weights, region) / total).astype(np.uint8).astype(int)
    diff = np.abs(gpu - cpu)
    print(f"        [GPU weighted_mean] gpu={gpu.tolist()} cpu={cpu.tolist()} "
          f"max_diff={int(diff.max())}")
    assert np.all(diff <= 2), f"GPU weighted mean diverges from CPU: {gpu} vs {cpu}"


def test_gpu_weighted_mean_zero_weights():
    """Degenerate all-zero weights must return black, never NaN/raise."""
    from ambilight.gpu import GpuAccelerator, GpuBackend
    acc = GpuAccelerator(GpuBackend.CUPY)
    region = (np.random.rand(100, 3) * 255).astype(np.float32)
    weights = np.zeros(100, dtype=np.float32)
    out = acc.weighted_mean_color(region, weights)
    assert out.tolist() == [0, 0, 0]


def test_gpu_vs_cpu_perf_smoke():
    """Informational throughput comparison — prints, asserts only correctness."""
    from ambilight.gpu import GpuAccelerator, GpuBackend
    gpu_acc = GpuAccelerator(GpuBackend.CUPY)
    cpu_acc = GpuAccelerator(GpuBackend.CPU)
    region = (np.random.rand(80 * 45, 3) * 255).astype(np.float32)
    weights = np.random.rand(80 * 45).astype(np.float32)
    iters = 500

    # Warm up CUDA context / kernels first (excluded from timing).
    for _ in range(10):
        gpu_acc.weighted_mean_color(region, weights)

    t0 = time.perf_counter()
    for _ in range(iters):
        g = gpu_acc.weighted_mean_color(region, weights)
    gpu_ms = (time.perf_counter() - t0) / iters * 1000

    t0 = time.perf_counter()
    for _ in range(iters):
        c = cpu_acc.weighted_mean_color(region, weights)
    cpu_ms = (time.perf_counter() - t0) / iters * 1000

    print(f"        [perf] weighted_mean over {region.shape[0]} px: "
          f"GPU={gpu_ms:.3f}ms  CPU={cpu_ms:.3f}ms  (n={iters})")
    assert np.all(np.abs(g.astype(int) - c.astype(int)) <= 2)


# ===========================================================================
# Capture backends  (require a live display)
# ===========================================================================

def test_dxgi_dxcam_live_grab():
    """dxcam DXGI backend: open primary monitor and deliver a real frame.

    Regression guard for the Optimus/hybrid-graphics bug: dxcam defaults to GPU
    device 0 (the discrete GPU), which duplicates BLACK on laptops whose panel is
    driven by the integrated GPU. We use WGC on the *same* monitor as a reference
    — if WGC sees content but DXGI is black, the adapter-selection fix regressed.
    A genuinely dark/DRM screen (WGC also black) skips the non-black assertion.
    """
    from ambilight.capture import DXGIBackend, WGCBackend, is_black_frame
    b = DXGIBackend()
    if not b.open(0):
        # dxcam.create() can fail to initialise D3D/DXGI when COM was already
        # set up in a conflicting apartment by an EARLIER test in the same
        # interpreter (the soundcard-backed audio effect in test_effects does
        # this). That's a process-isolation artifact, not a code regression —
        # the module passes 12/12 when run on its own:
        #   pytest tests/test_live_hardware.py
        pytest.skip(
            "dxcam could not initialise in this interpreter (COM-apartment "
            "contamination from an earlier soundcard/WinRT test). Run the live "
            "hardware module standalone to exercise DXGI."
        )
    try:
        frame = _grab_until(b, tries=120, delay=0.03)
        assert frame is not None, "dxcam opened but delivered no frame"
        assert frame.ndim == 3 and frame.shape[2] == 3
        assert frame.dtype == np.uint8
        dxgi_black = is_black_frame(frame)
        _report("DXGI", frame)
        _save("dxgi_primary.png", frame)
    finally:
        b.close()
        _dxcam_cleanup()

    # Same-monitor reference: is there visible content on the primary at all?
    ref = WGCBackend()
    ref_black = True
    if ref.open(0, target_size=(480, 270), fps_target=30):
        try:
            rframe = _grab_until(ref, tries=120, delay=0.03)
            ref_black = rframe is None or is_black_frame(rframe)
        finally:
            ref.close()
    if not ref_black:
        assert not dxgi_black, (
            "DXGI returned an all-black frame while WGC captured content on the "
            "same monitor — the dxcam adapter-selection (Optimus) fix has "
            "regressed: DXGI is duplicating the discrete GPU instead of the "
            "iGPU that drives the panel."
        )


def test_wgc_live_grab():
    """Windows Graphics Capture backend: open primary monitor, deliver a frame."""
    from ambilight.capture import WGCBackend
    b = WGCBackend()
    if not b.open(0, target_size=(480, 270), fps_target=30):
        pytest.skip("WGC (windows-capture) unavailable on this machine")
    try:
        frame = _grab_until(b, tries=120, delay=0.03)
        assert frame is not None, "WGC opened but delivered no frame"
        assert frame.shape == (270, 480, 3)
        assert frame.dtype == np.uint8
        _report("WGC", frame)
        _save("wgc_primary.png", frame)
    finally:
        b.close()


def test_mss_live_grab():
    """MSS fallback backend: open primary monitor, deliver a frame."""
    from ambilight.capture import MSSBackend
    b = MSSBackend()
    assert b.open(0) is True, "MSSBackend failed to open monitor 0"
    try:
        frame = _grab_until(b, tries=40, delay=0.03)
        assert frame is not None, "MSS delivered no frame"
        assert frame.ndim == 3 and frame.shape[2] == 3
        assert frame.dtype == np.uint8
        _report("MSS", frame)
        _save("mss_primary.png", frame)
    finally:
        b.close()


def test_manager_live_selection_and_grab():
    """Full ScreenCaptureManager: pick the best real backend and grab a frame."""
    from ambilight.capture import ScreenCaptureManager
    mgr = ScreenCaptureManager(
        preferred_method="wgc", monitor_index=0, fps_target=30,
        analysis_width=80, analysis_height=45,
    )
    mgr.start()
    try:
        assert mgr.active_backend in {"wgc", "dxgi", "mss"}
        print(f"        [Manager] selected backend: {mgr.active_backend}")
        frame = None
        for _ in range(150):
            frame = mgr.grab()
            if frame is not None:
                break
        assert frame is not None, (
            f"manager active={mgr.active_backend} delivered no frame"
        )
        assert frame.ndim == 3 and frame.shape[2] == 3
        assert mgr.is_healthy is True
        _report(f"Manager/{mgr.active_backend}", frame)
    finally:
        mgr.stop()
        _dxcam_cleanup()
