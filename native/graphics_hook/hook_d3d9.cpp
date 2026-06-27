// hook_d3d9.cpp — see hook_d3d9.h.
//
// Obtains the IDirect3DDevice9 vtable from a throwaway dummy device and VMT-hooks
// Present (slot 17). The detour copies the backbuffer to a system-memory surface
// (GetRenderTargetData), converts to BGR, and publishes it.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <d3d9.h>

#include <chrono>
#include <vector>

#include "hook_d3d9.h"
#include "shm_writer.h"
#include "hook_control.h"
#include "capture_util.h"
#include "hooklog.h"

#include <MinHook.h>

namespace ambilight {

namespace {

using D9Present_t = HRESULT(STDMETHODCALLTYPE*)(IDirect3DDevice9*, const RECT*, const RECT*,
                                                HWND, const RGNDATA*);
using Direct3DCreate9_t = IDirect3D9*(WINAPI*)(UINT);

constexpr unsigned kD9PresentSlot = 17;  // IDirect3DDevice9::Present

ShmWriter* g_writer = nullptr;
const HookControl* g_control = nullptr;
D9Present_t g_orig_present = nullptr;
long long g_frame_interval_us = 33333;
std::vector<uint8_t> g_scratch;
std::chrono::steady_clock::time_point g_last_capture{};
bool g_logged_first = false;
bool g_warned_rtdata = false;
uint32_t g_warned_fmt = 0;

long long now_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

void capture_d3d9(IDirect3DDevice9* dev) {
    const auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::microseconds>(now - g_last_capture).count()
            < g_frame_interval_us) {
        return;
    }
    if (g_control && g_control->stop) return;
    if (g_writer == nullptr) return;

    static int fg_gate = -1;
    if (fg_gate == -1) {
        wchar_t v[8] = {0};
        const DWORD n = GetEnvironmentVariableW(L"AMBILIGHT_HOOK_CAPTURE_ALL", v, 8);
        fg_gate = (n > 0 && v[0] == L'1') ? 0 : 1;
    }
    if (fg_gate) {
        D3DDEVICE_CREATION_PARAMETERS cp{};
        if (SUCCEEDED(dev->GetCreationParameters(&cp)) && cp.hFocusWindow &&
            cp.hFocusWindow != GetForegroundWindow()) {
            return;
        }
    }

    IDirect3DSurface9* back = nullptr;
    if (FAILED(dev->GetBackBuffer(0, 0, D3DBACKBUFFER_TYPE_MONO, &back)) || back == nullptr) {
        return;
    }
    D3DSURFACE_DESC sd{};
    back->GetDesc(&sd);

    IDirect3DSurface9* sys = nullptr;
    if (SUCCEEDED(dev->CreateOffscreenPlainSurface(sd.Width, sd.Height, sd.Format,
                                                   D3DPOOL_SYSTEMMEM, &sys, nullptr)) &&
        sys != nullptr) {
        // GetRenderTargetData pulls the GPU backbuffer into our lockable sysmem
        // surface (fails for multisampled backbuffers — rare; skipped).
        if (SUCCEEDED(dev->GetRenderTargetData(back, sys))) {
            D3DLOCKED_RECT lr{};
            if (SUCCEEDED(sys->LockRect(&lr, nullptr, D3DLOCK_READONLY))) {
                if (d3d9_to_bgr(static_cast<const uint8_t*>(lr.pBits), lr.Pitch, sd.Width,
                                sd.Height, static_cast<uint32_t>(sd.Format), g_scratch)) {
                    if (g_writer->write_frame(g_scratch.data(), sd.Width, sd.Height,
                                              static_cast<uint64_t>(now_us()))) {
                        g_last_capture = now;
                        if (!g_logged_first) {
                            hook_log("D3D9 capture live: %ux%u fmt=%u", sd.Width, sd.Height,
                                     static_cast<uint32_t>(sd.Format));
                            g_logged_first = true;
                        }
                    }
                } else if (g_warned_fmt != static_cast<uint32_t>(sd.Format)) {
                    hook_log("unsupported D3D9 format %u (SDR only); skipping",
                             static_cast<uint32_t>(sd.Format));
                    g_warned_fmt = static_cast<uint32_t>(sd.Format);
                }
                sys->UnlockRect();
            }
        } else if (!g_warned_rtdata) {
            hook_log("D3D9 GetRenderTargetData failed (multisampled backbuffer?); skipping");
            g_warned_rtdata = true;
        }
        sys->Release();
    }
    back->Release();
}

HRESULT STDMETHODCALLTYPE D9Present_detour(IDirect3DDevice9* self, const RECT* src,
                                           const RECT* dst, HWND wnd, const RGNDATA* dirty) {
    __try {
        capture_d3d9(self);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
    return g_orig_present(self, src, dst, wnd, dirty);
}

}  // namespace

bool install_d3d9_hook(ShmWriter* writer, const HookControl* control) {
    HMODULE d3d9 = GetModuleHandleW(L"d3d9.dll");
    if (d3d9 == nullptr) return false;  // not a D3D9 game
    auto create = reinterpret_cast<Direct3DCreate9_t>(GetProcAddress(d3d9, "Direct3DCreate9"));
    if (create == nullptr) return false;

    g_writer = writer;
    g_control = control;
    const uint32_t fps = (control && control->fps) ? control->fps : 30;
    g_frame_interval_us = 1000000ll / (fps ? fps : 30);

    IDirect3D9* d3d = create(D3D_SDK_VERSION);
    if (d3d == nullptr) {
        hook_log("D3D9 hook: Direct3DCreate9 failed");
        return false;
    }

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"AmbilightDummyD3D9";
    RegisterClassExW(&wc);
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"", WS_OVERLAPPEDWINDOW, 0, 0, 8, 8,
                               nullptr, nullptr, wc.hInstance, nullptr);

    D3DPRESENT_PARAMETERS pp{};
    pp.Windowed = TRUE;
    pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.BackBufferFormat = D3DFMT_X8R8G8B8;
    pp.BackBufferWidth = 8;
    pp.BackBufferHeight = 8;
    pp.BackBufferCount = 1;
    pp.hDeviceWindow = hwnd;

    IDirect3DDevice9* dev = nullptr;
    HRESULT hr = d3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, hwnd,
                                   D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &dev);
    if (FAILED(hr)) {
        hr = d3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_REF, hwnd,
                               D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &dev);
    }

    // D3D9 device vtables are PER-INSTANCE (verified), so a VMT swap on this dummy
    // would not affect the game's device. Instead read the shared Present *code
    // address* from the dummy's vtable and inline-hook it with MinHook — that one
    // address is the same for every device created by this d3d9.dll.
    void* present_addr = nullptr;
    if (SUCCEEDED(hr) && dev != nullptr) {
        void** vtable = *reinterpret_cast<void***>(dev);
        present_addr = vtable[kD9PresentSlot];
        dev->Release();
    } else {
        hook_log("D3D9 hook: CreateDevice failed 0x%08lx", hr);
    }
    d3d->Release();
    if (hwnd) DestroyWindow(hwnd);

    if (present_addr == nullptr) return false;

    if (MH_CreateHook(present_addr, reinterpret_cast<LPVOID>(&D9Present_detour),
                      reinterpret_cast<LPVOID*>(&g_orig_present)) != MH_OK ||
        MH_EnableHook(present_addr) != MH_OK) {
        hook_log("D3D9 hook: MinHook failed to hook Present");
        return false;
    }
    hook_log("D3D9 hook installed (Present @ %p), fps=%u", present_addr, fps);
    return true;
}

}  // namespace ambilight
