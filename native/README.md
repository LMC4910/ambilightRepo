# native/ — game capture (DirectX 9 / 10 / 11 / 12 + Vulkan hook)

Native components that let the Python colour pipeline receive frames from a game
running in **exclusive/borderless fullscreen Direct3D or Vulkan**, which the
compositor-based backends (WGC / DXGI / MSS) cannot reach.

The Python side is `ambilight/hook_capture.py` (`HookCaptureBackend`). It is
**opt-in only** — selected via `capture.method: hook` in `configuration.yaml` —
and never joins the automatic WGC→DXGI→MSS fallback chain. When no game is
foreground the hook delivers no frames, so the manager falls back to desktop
capture; when a game goes fullscreen the hook takes over.

## Layout

```
native/
  shared_memory/
    shm_protocol.h     Canonical frame ring-buffer wire format (mirrored in hook_capture.py).
    shm_writer.{h,cpp} Ring-buffer slot writer (seqlock); shared lib `ambshm`.
    hook_control.h     Fixed-name control mapping (frame-buffer name + fps + stop).
  capture_host/        capture_host.exe — detects the foreground game, injects the DLL.
    main.cpp             CLI + fake-frame source + hook-mode detect/inject loop.
    detect.{h,cpp}       Foreground + fullscreen + Direct3D-module "is it a game" gate.
    inject.{h,cpp}       SeDebugPrivilege + CreateRemoteThread(LoadLibraryW) injection.
  graphics_hook/       graphics_hook.dll — injected into the game; hooks Present.
    dllmain.cpp          Bootstrap: control mapping → ShmWriter → install hooks.
    hook_dxgi.{h,cpp}    DXGI Present hook → DX10 / DX11 / DX12 capture.
    hook_d3d9.{h,cpp}    Direct3D 9 Present hook.
    hook_vulkan.{h,cpp}  vkQueuePresentKHR hook → Vulkan swapchain capture.
    capture_util.{h,cpp} Backbuffer format → BGR conversion.
    vmt_hook.{h,cpp}     Vtable hooking (DXGI).
  third_party/minhook/        Vendored MinHook (BSD-2) — inline hooks for DX9/DX12/Vulkan.
  third_party/vulkan-headers/ Vendored Khronos Vulkan-Headers (Apache-2.0) — headers only.
  test_dx11/           dx9/dx11/dx12 probe apps (not shipped) for headless tests.
```

## Architecture

```
capture_host.exe --mode hook --target <auto|exe>
  detect foreground fullscreen Direct3D game → inject graphics_hook.dll
  control mapping hands the DLL the frame-buffer name + fps

graphics_hook.dll (inside the game)
  hook Present → copy backbuffer → BGR → ShmWriter → Python-owned ring buffer
```

Python **owns** the frame buffer, so a host/DLL crash never crashes Python. The
DLL only writes when its window is foreground (so multiple injected games never
fight), throttles to `fps`, and always calls the original `Present` (SEH-guarded)
— it never breaks the game.

### Hooking mechanism

- **DXGI** (DX10/11/12): the `IDXGISwapChain` vtable is shared across instances,
  so a **VMT hook** (vtable-slot swap) on a dummy swapchain intercepts the game's
  swapchain too — dependency-free.
- **D3D9 / D3D12**: device/queue vtables are **per-instance**, so VMT can't reach
  the game's object. We read the shared function *code address* and **inline-hook**
  it with [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2, vendored under
  `third_party/minhook`). DX12 also needs a command queue, captured by hooking
  `ID3D12CommandQueue::ExecuteCommandLists`.
- **Vulkan**: MinHook the exported `vulkan-1.dll` entry points. `vkCreateSwapchainKHR`
  is hooked to add `VK_IMAGE_USAGE_TRANSFER_SRC_BIT` (so the swapchain image is
  copyable) and to record the device/format/extent + images; `vkQueuePresentKHR`
  records a one-shot copy of the presented image to a host-visible buffer (submitted
  on the present queue, fenced) → BGR. Memory types come from a throwaway probe
  instance (correct on single-GPU systems), so we needn't observe `vkCreateDevice`,
  which runs before injection. A swapchain created **before** injection is captured
  only once it is recreated (fullscreen entry/resize, or an alt-tab out/in).

`graphics_hook.dll` resolves every DirectX `Create*` and Vulkan `vk*` function at
runtime (GetProcAddress), so it imports only KERNEL32 + USER32 — injecting into any
game forces no extra D3D / Vulkan DLLs to load.

## Building

Requires CMake ≥ 3.20, a Windows C++ toolchain (MSVC recommended), and the
Windows SDK. From the repo root, `python build.py --native` builds everything and
prefers the MSVC/Visual Studio toolchain automatically. Or directly:

```bash
cmake -S native -B native/build -G "Visual Studio 16 2019" -A x64
cmake --build native/build --config Release
```

Both `capture_host.exe` and `graphics_hook.dll` land in `native/build/bin[/Release]`
(co-located so the host finds the DLL next to itself). `build.py` bundles both into
the PyInstaller service onedir via `--add-binary`.

## CLI (`capture_host.exe`)

| Flag             | Meaning                                                          |
|------------------|-----------------------------------------------------------------|
| `--shm-name N`   | Name of the Python-created frame mapping (required).            |
| `--fps N`        | Target capture frame rate (1–240, default 30).                  |
| `--mode fake`    | Animated test source (used by the transport tests).            |
| `--mode hook`    | Real game capture: detect + inject.                            |
| `--target auto`  | Any fullscreen game (default), or a substring exe filter.      |
| `--inject-pid N` | Force-inject a specific pid (manual testing / detection misses).|
| `--parent-pid N` | Exit when this process exits (orphan safety).                  |

## Diagnostics

- `capture_host` logs detection/injection decisions to `~/.ambilight/logs/capture_host.log`.
- `graphics_hook.dll` logs which API it hooked + capture status to
  `~/.ambilight/logs/graphics_hook.log` (and OutputDebugString).
- `AMBILIGHT_HOOK_CAPTURE_ALL=1` (env in the *game*) disables the foreground gate
  — useful for the probes or a game that renders on a non-foreground child window.

## Caveats

> ⚠️ **Anti-cheat.** Injecting a DLL into a game can be detected by anti-cheat
> (BattlEye, EAC, Riot Vanguard) and may result in an account **ban**. Test only
> on games **without** kernel-level anti-cheat. If anti-cheat compatibility
> matters, the OBS Game Capture + Spout route (`prototype/obs_spout/`) is
> whitelisted and never touches the game process.

- **Elevation:** injecting into an elevated game (admin / launcher) requires the
  Ambilight service to run elevated; otherwise injection fails with access-denied
  (logged).
- **Bitness:** x64 host injects an x64 DLL into x64 games (the norm). 32-bit games
  are skipped (logged).
- **SDR only:** 10-bit / HDR (`R10G10B10A2`, Vulkan `A2B10G10R10`) and multisampled
  backbuffers are skipped with a one-time warning.
- **Vulkan specifics:** capture starts on the first swapchain (re)created *after*
  injection — a game already fullscreen when capture starts may need one fullscreen
  toggle / alt-tab to recreate it. Hooking the `vulkan-1.dll` loader exports catches
  games that present through the loader (the vast majority); a game using a custom
  loader/`volk` dispatch that bypasses the exports won't be caught (a Vulkan layer
  would be the more-robust route). Host-visible memory types are read from a probe
  instance, assuming the game runs on the system's primary/discrete GPU.
