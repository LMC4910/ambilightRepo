# native/ — game capture host (DirectX 11 hook)

Native components that let the Python colour pipeline receive frames from a game
running in **exclusive fullscreen DirectX 11**, which the compositor-based
backends (WGC / DXGI / MSS) cannot reach.

The Python side is `ambilight/hook_capture.py` (`HookCaptureBackend`). It is
**opt-in only** — selected via `capture.method: hook` in `configuration.yaml` —
and never joins the automatic WGC→DXGI→MSS fallback chain.

## Layout

```
native/
  shared_memory/shm_protocol.h   Canonical shared-memory wire format (single
                                 source of truth; mirrored in hook_capture.py).
  capture_host/                  capture_host.exe — attaches to the Python-owned
                                 shared mapping and writes frames into it.
    main.cpp                       CLI + Phase-1 fake animated frame generator.
    shm_writer.{h,cpp}             Ring-buffer slot writer (seqlock protocol).
  graphics_hook/                 (Phase 2) injected DLL that hooks
                                 IDXGISwapChain::Present and copies the backbuffer.
```

## Architecture

```
Python (owns shared memory)            capture_host.exe
  HookCaptureBackend.open()
    create SharedMemory   ──┐
    launch capture_host  ───┼──► OpenFileMapping, validate, write frames
  grab()  ← read newest ◄───┘      (ring buffer, newest-frame-wins)
```

Python **owns** the mapping, so a host crash never tears it down or crashes
Python — `grab()` just returns the last/None frame and the backend relaunches
the host. The host is a child process; it self-exits when stdin closes (Python
gone) or its `--parent-pid` dies.

## Building

Requires CMake ≥ 3.20, a Windows C++ toolchain (MSVC or clang-cl), and the
Windows SDK. From this directory:

```bash
cmake -S . -B build
cmake --build build --config Release
```

The host lands at `native/build/capture_host/capture_host.exe` (Ninja) or
`native/build/capture_host/Release/capture_host.exe` (Visual Studio generator).
`ambilight/hook_capture.py` searches both locations in dev; the release build
bundles the exe via PyInstaller (`build.py`).

### Manual smoke test (fake frames)

```bash
capture_host.exe --shm-name <name> --fps 30 --mode fake
```

You normally don't run this by hand — `HookCaptureBackend.open()` launches it
with a freshly created shared-memory name. See `tests/test_hook_capture.py`.

## CLI

| Flag            | Meaning                                                    |
|-----------------|------------------------------------------------------------|
| `--shm-name N`  | Name of the Python-created shared mapping (required).      |
| `--fps N`       | Target frame rate (1–240, default 30).                     |
| `--mode fake`   | Frame source. Phase 1 supports only `fake`.                |
| `--parent-pid N`| Exit when this process exits (orphan safety).              |

## Phase 2 — real DX11 hook (not yet implemented)

`graphics_hook.dll` will hook `IDXGISwapChain::Present()`, copy the backbuffer,
and publish frames through the **same** `ShmWriter` and protocol. `capture_host`
gains `--mode hook --target <exe>` to inject the DLL. None of the Phase-1
transport changes — only the frame *source* swaps from fake to real.

> ⚠️ **Anti-cheat warning (Phase 2 only).** Injecting a DLL into a game process
> can be detected by anti-cheat systems (BattlEye, EAC, Riot Vanguard) and may
> result in an account ban. This is intended for the user's own SDR DX11 titles;
> test only on games **without** kernel-level anti-cheat. Phase 1 (fake frames)
> performs no injection and carries no such risk. If anti-cheat compatibility
> matters, the OBS Game Capture + Spout route (see `prototype/obs_spout/`) is
> whitelisted and never touches the game process.
