"""
Hook capture backend
=====================
Receives frames from an exclusive-fullscreen DirectX 11 game via a native helper
process (``capture_host.exe``) over shared memory. This is the **opt-in** backend
selected with ``capture.method: hook``; it never joins the automatic
WGC→DXGI→MSS fallback chain (injecting into / hooking a game process should not
happen silently).

Architecture
------------
Python **owns** the shared memory; the native host **attaches** to it::

    HookCaptureBackend.open()
        SharedFrameBuffer.create()      # Python creates + initialises the mapping
        CaptureHostProcess.launch()     # spawn capture_host.exe, pass the SHM name
    HookCaptureBackend.grab()
        SharedFrameBuffer.read_latest() # newest completed ring slot -> BGR ndarray
    HookCaptureBackend.close()
        kill host, free SHM

Because Python owns the mapping, a host crash never tears it down or crashes
Python: ``grab()`` simply stops seeing new frames, the backend relaunches the
host with back-off, and (if it stays dead) returns *None* so the manager can fall
back. The wire format is defined once in ``native/shared_memory/shm_protocol.h``
and mirrored by the ``struct`` layouts below — keep the two in sync.

Phase 1 drives this with the host's *fake* animated frame generator, proving the
whole transport before any real DLL injection / ``Present()`` hook exists.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import sys
import time
from contextlib import suppress
from multiprocessing import shared_memory
from typing import Optional

import numpy as np

from .capture import CaptureBackend, _as_target
from .paths import is_frozen, resource_path, user_data_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared-memory protocol — mirrors native/shared_memory/shm_protocol.h.
# Bump SHM_VERSION on both sides together if any layout below changes.
# ---------------------------------------------------------------------------

SHM_MAGIC = 0x484D4241  # 'AMBH' little-endian
SHM_VERSION = 1
SHM_FORMAT_BGR = 0
SHM_NO_FRAME = -1

CONTROL_BLOCK_SIZE = 64
SLOT_HEADER_SIZE = 64
SLOT_COUNT = 3
CHANNELS = 3

# ControlBlock @ offset 0 (64 bytes):
#   magic u32, version u32, slot_count u32, max_width u32, max_height u32,
#   channels u32, slot_stride u32, reserved0 u32, latest_index i64, reserved1[24]
_CTRL_HEAD = struct.Struct("<8I")          # magic..reserved0 (32 bytes)
_LATEST_INDEX = struct.Struct("<q")        # latest_index @ offset 32
_LATEST_INDEX_OFF = 32

# SlotHeader @ slot start (64 bytes):
#   seq u32, width u32, height u32, format u32, byte_size u32, reserved0 u32,
#   frame_id u64, timestamp_us u64, reserved1[24]
_SLOT_SEQ = struct.Struct("<I")            # seq @ slot+0
_SLOT_BODY = struct.Struct("<6I2Q")        # seq..timestamp_us (40 bytes)

# Belt-and-suspenders: a torn read should be rare (3 slots, reader keeps up), so
# a few retries always wins. Beyond that we report "no fresh frame".
_MAX_SEQLOCK_RETRIES = 5


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


class SharedFrameBuffer:
    """Owns the shared-memory ring buffer the native host writes into.

    Python creates and owns the mapping so its lifetime outlives any host crash.
    The host opens it by ``name`` and publishes frames; ``read_latest`` returns
    the newest completed frame (or *None* if none is ready / a read tore).
    """

    def __init__(self, max_width: int, max_height: int,
                 slot_count: int = SLOT_COUNT) -> None:
        self.max_width = int(max_width)
        self.max_height = int(max_height)
        self.slot_count = int(slot_count)
        # Each slot holds the header + a full max-size frame, padded to 64 bytes.
        pixel_bytes = self.max_width * self.max_height * CHANNELS
        self.slot_stride = _align_up(SLOT_HEADER_SIZE + pixel_bytes, 64)
        total = CONTROL_BLOCK_SIZE + self.slot_count * self.slot_stride

        self._shm: Optional[shared_memory.SharedMemory] = shared_memory.SharedMemory(
            create=True, size=total
        )
        self._buf = self._shm.buf
        self.last_frame_id: int = -1

        # The mapping is zero-initialised by the OS (so every slot seq starts even
        # at 0); we only need to stamp the ControlBlock and arm latest_index.
        _CTRL_HEAD.pack_into(
            self._buf, 0,
            SHM_MAGIC, SHM_VERSION, self.slot_count,
            self.max_width, self.max_height, CHANNELS,
            self.slot_stride, 0,
        )
        _LATEST_INDEX.pack_into(self._buf, _LATEST_INDEX_OFF, SHM_NO_FRAME)

    @property
    def name(self) -> str:
        assert self._shm is not None
        return self._shm.name

    def _slot_offset(self, index: int) -> int:
        return CONTROL_BLOCK_SIZE + index * self.slot_stride

    def read_latest(self) -> Optional["tuple[int, np.ndarray]"]:
        """Return ``(frame_id, BGR ndarray (H,W,3) uint8)`` for the newest
        completed frame, or *None* when none is ready or a read tore.

        The returned array is a private copy, decoupled from shared memory, so
        the host overwriting the slot afterwards cannot corrupt it.
        """
        if self._shm is None:
            return None
        idx = _LATEST_INDEX.unpack_from(self._buf, _LATEST_INDEX_OFF)[0]
        if idx == SHM_NO_FRAME or not (0 <= idx < self.slot_count):
            return None

        slot_off = self._slot_offset(idx)
        for _ in range(_MAX_SEQLOCK_RETRIES):
            seq1 = _SLOT_SEQ.unpack_from(self._buf, slot_off)[0]
            if seq1 & 1:
                continue  # writer mid-write; retry
            (_, width, height, fmt, byte_size, _,
             frame_id, _ts) = _SLOT_BODY.unpack_from(self._buf, slot_off)

            if (fmt != SHM_FORMAT_BGR or width == 0 or height == 0
                    or width > self.max_width or height > self.max_height
                    or byte_size != width * height * CHANNELS):
                return None  # malformed slot — treat as no frame

            pix_off = slot_off + SLOT_HEADER_SIZE
            frame = np.frombuffer(
                self._buf, dtype=np.uint8, count=byte_size, offset=pix_off
            ).reshape((height, width, CHANNELS)).copy()

            # Seqlock close: the slot must still be stable and unchanged.
            seq2 = _SLOT_SEQ.unpack_from(self._buf, slot_off)[0]
            if seq2 == seq1:
                self.last_frame_id = frame_id
                return frame_id, frame
            # else the host overwrote this slot mid-copy; retry
        return None

    def close(self) -> None:
        if self._shm is not None:
            shm, self._shm, self._buf = self._shm, None, None
            with suppress(Exception):  # best-effort teardown
                shm.close()
            with suppress(Exception):
                shm.unlink()  # no-op on Windows; frees the mapping on POSIX


class CaptureHostProcess:
    """Launches and supervises ``capture_host.exe``.

    Resolves the binary for both frozen (bundled) and dev (CMake build output)
    layouts, spawns it windowless with the shared-memory name, and relaunches it
    with back-off if it dies. Closing our end of its stdin (or this process
    dying) makes the host self-exit, so it never lingers as an orphan.
    """

    _EXE_NAME = "capture_host.exe"

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._exe: Optional[str] = None
        self._errlog = None

    @classmethod
    def resolve_exe(cls) -> Optional[str]:
        """First existing path to the host binary, or *None* if not built."""
        candidates: "list[str]" = []
        if is_frozen():
            candidates.append(resource_path(os.path.join("native", cls._EXE_NAME)))
        # Dev: two levels up from this file is the repo root.
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        native = os.path.join(repo_root, "native")
        candidates += [
            os.path.join(native, "build", "capture_host", cls._EXE_NAME),         # Ninja
            os.path.join(native, "build", "capture_host", "Release", cls._EXE_NAME),  # VS gen
            os.path.join(native, "build", "Release", cls._EXE_NAME),               # legacy
            os.path.join(native, cls._EXE_NAME),                                   # prebuilt
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def launch(self, shm_name: str, fps: int) -> bool:
        """(Re)launch the host attached to *shm_name*. Returns False if the
        binary is missing or the spawn fails."""
        self.stop()
        exe = self.resolve_exe()
        if exe is None:
            return False
        self._exe = exe

        args = [
            exe,
            "--shm-name", shm_name,
            "--fps", str(int(fps)),
            "--mode", "fake",
            "--parent-pid", str(os.getpid()),
        ]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        # Route the host's diagnostic stderr to a logfile (same convention as the
        # service). stdin is a pipe whose EOF tells the host to exit.
        try:
            self._errlog = open(
                os.path.join(_logs_dir(), "capture_host.log"), "ab", buffering=0
            )
        except Exception:  # noqa: BLE001 — logging must never break capture
            self._errlog = subprocess.DEVNULL
        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._errlog,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Capture] failed to launch capture_host: %s", exc)
            return False
        logger.info("[Capture] launched capture_host (pid=%s)", self._proc.pid)
        return True

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            # Closing stdin signals a clean exit; terminate if it lingers.
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.wait(timeout=1.0)
            except Exception:  # noqa: BLE001
                with suppress(Exception):
                    proc.terminate()
                with suppress(Exception):
                    proc.wait(timeout=1.0)
        if self._errlog not in (None, subprocess.DEVNULL):
            with suppress(Exception):
                self._errlog.close()
        self._errlog = None


class HookCaptureBackend(CaptureBackend):
    """Opt-in capture backend that sources frames from a DX11 game via the native
    host over shared memory. Matches the :class:`CaptureBackend` contract so the
    rest of the pipeline is unchanged.
    """

    name = "hook"

    _DEFAULT_MAX = (1920, 1080)
    _WARMUP_S = 1.5       # wait this long for the first frame on open()
    _STALE_S = 1.0        # frame_id stuck longer than this => treat as failure
    _RELAUNCH_MAX_S = 5.0

    def __init__(self) -> None:
        self._buffer: Optional[SharedFrameBuffer] = None
        self._host: Optional[CaptureHostProcess] = None
        self._target_size: Optional["tuple[int, int]"] = None
        self._fps = 30
        self._available = False
        self._last_frame: Optional[np.ndarray] = None
        self._last_seen_id = -1
        self._last_advance_t = 0.0
        self._next_relaunch_at = 0.0
        self._relaunch_attempts = 0

    # ------------------------------------------------------------------
    # CaptureBackend interface
    # ------------------------------------------------------------------

    def open(self, target, target_size=None, fps_target: int = 30) -> bool:
        # Unavailable (non-Windows, or the native host was never built) -> let the
        # manager promote the next backend instead of erroring.
        if CaptureHostProcess.resolve_exe() is None:
            logger.info(
                "[Capture] hook backend unavailable: %s not found "
                "(build native/ first)", CaptureHostProcess._EXE_NAME
            )
            return False

        t = _as_target(target)
        max_w = int(t.get("width") or 0) or self._DEFAULT_MAX[0]
        max_h = int(t.get("height") or 0) or self._DEFAULT_MAX[1]

        try:
            self._buffer = SharedFrameBuffer(max_w, max_h)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Capture] hook: could not create shared memory: %s", exc)
            self._cleanup()
            return False

        self._host = CaptureHostProcess()
        if not self._host.launch(self._buffer.name, fps_target):
            logger.info("[Capture] hook: capture_host failed to launch")
            self._cleanup()
            return False

        self._target_size = target_size
        self._fps = int(fps_target)
        self._available = True
        self._last_seen_id = -1
        self._last_advance_t = time.monotonic()
        self._relaunch_attempts = 0
        self._next_relaunch_at = 0.0

        # Warm-up: give the host a moment to publish its first frame.
        deadline = time.monotonic() + self._WARMUP_S
        while time.monotonic() < deadline:
            if self._buffer.read_latest() is not None:
                break
            time.sleep(0.02)
        return True

    def grab(self) -> Optional[np.ndarray]:
        if not self._available or self._buffer is None:
            return None

        latest = self._buffer.read_latest()
        now = time.monotonic()

        if latest is not None:
            frame_id, frame = latest
            if frame_id != self._last_seen_id:
                self._last_seen_id = frame_id
                self._last_advance_t = now
                self._relaunch_attempts = 0  # healthy again
            out = _downscale(frame, self._target_size)
            self._last_frame = out

            # Host stalled (frames stopped advancing) -> report failure so the
            # manager can fall back; relaunch if the process actually died.
            if now - self._last_advance_t > self._STALE_S:
                if self._host is not None and not self._host.is_alive():
                    self._maybe_relaunch()
                return None
            return out

        # No frame yet (startup) or a torn read. If the host died, relaunch and
        # report failure; otherwise hand back the last good frame to avoid flicker.
        if self._host is not None and not self._host.is_alive():
            self._maybe_relaunch()
            return None
        return self._last_frame

    def close(self) -> None:
        self._cleanup()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _maybe_relaunch(self) -> None:
        now = time.monotonic()
        if now < self._next_relaunch_at or self._buffer is None or self._host is None:
            return
        backoff = min(0.5 * (2 ** self._relaunch_attempts), self._RELAUNCH_MAX_S)
        self._next_relaunch_at = now + backoff
        self._relaunch_attempts += 1
        logger.info("[Capture] hook: relaunching capture_host (attempt %d)",
                    self._relaunch_attempts)
        self._host.launch(self._buffer.name, self._fps)
        self._last_advance_t = now  # give the new host time before judging it again

    def _cleanup(self) -> None:
        self._available = False
        if self._host is not None:
            with suppress(Exception):
                self._host.stop()
            self._host = None
        if self._buffer is not None:
            with suppress(Exception):
                self._buffer.close()
            self._buffer = None
        self._last_frame = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _downscale(frame: np.ndarray, target_size) -> np.ndarray:
    """Pre-downscale a BGR frame to ``target_size`` = ``(width, height)``,
    mirroring the WGC backend's behaviour. Channel order is preserved (PIL's
    bilinear resize is per-channel, so feeding it BGR returns BGR)."""
    if target_size is None:
        return frame
    tw, th = target_size
    if not tw or not th:
        return frame
    if frame.shape[1] == tw and frame.shape[0] == th:
        return frame
    from PIL import Image
    return np.asarray(Image.fromarray(frame).resize((tw, th), Image.BILINEAR))


def _logs_dir() -> str:
    d = os.path.join(str(user_data_dir()), "logs")
    os.makedirs(d, exist_ok=True)
    return d
