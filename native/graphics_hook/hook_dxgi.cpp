// hook_dxgi.cpp — see hook_dxgi.h.
//
// Obtains the IDXGISwapChain vtable from a throwaway dummy device+swapchain and
// VMT-hooks Present (slot 8) and ResizeBuffers (slot 13). Both blt-model
// (IDXGISwapChain) and flip-model (IDXGISwapChain1) swapchains share this vtable,
// so one hook covers DX10/DX11/DX12 games. The Present detour copies the
// backbuffer to a staging texture, converts to BGR, and publishes it.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>

#include <chrono>
#include <vector>

#include "hook_dxgi.h"
#include "shm_writer.h"
#include "hook_control.h"
#include "vmt_hook.h"
#include "capture_util.h"
#include "hooklog.h"

namespace ambilight {

namespace {

using Present_t = HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT);
using ResizeBuffers_t =
    HRESULT(STDMETHODCALLTYPE*)(IDXGISwapChain*, UINT, UINT, UINT, DXGI_FORMAT, UINT);

constexpr unsigned kPresentSlot = 8;
constexpr unsigned kResizeBuffersSlot = 13;

ShmWriter* g_writer = nullptr;
const HookControl* g_control = nullptr;
Present_t g_orig_present = nullptr;
ResizeBuffers_t g_orig_resize = nullptr;
long long g_frame_interval_us = 33333;  // 1e6 / fps

// Reused capture resources (Present runs on a single render thread).
ID3D11Texture2D* g_staging = nullptr;
ID3D11Device* g_staging_device = nullptr;
UINT g_staging_w = 0, g_staging_h = 0;
DXGI_FORMAT g_staging_fmt = DXGI_FORMAT_UNKNOWN;
std::vector<uint8_t> g_scratch;
std::chrono::steady_clock::time_point g_last_capture{};
DXGI_FORMAT g_warned_fmt = DXGI_FORMAT_UNKNOWN;
bool g_logged_first_frame = false;
bool g_logged_oversize = false;

long long now_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

void release_staging() {
    if (g_staging) { g_staging->Release(); g_staging = nullptr; }
    g_staging_device = nullptr;
    g_staging_w = g_staging_h = 0;
    g_staging_fmt = DXGI_FORMAT_UNKNOWN;
}

bool ensure_staging(ID3D11Device* dev, const D3D11_TEXTURE2D_DESC& bb) {
    if (g_staging && g_staging_device == dev && g_staging_w == bb.Width &&
        g_staging_h == bb.Height && g_staging_fmt == bb.Format) {
        return true;
    }
    release_staging();

    D3D11_TEXTURE2D_DESC sd{};
    sd.Width = bb.Width;
    sd.Height = bb.Height;
    sd.MipLevels = 1;
    sd.ArraySize = 1;
    sd.Format = bb.Format;
    sd.SampleDesc.Count = 1;
    sd.Usage = D3D11_USAGE_STAGING;
    sd.BindFlags = 0;
    sd.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    sd.MiscFlags = 0;
    if (FAILED(dev->CreateTexture2D(&sd, nullptr, &g_staging))) {
        g_staging = nullptr;
        return false;
    }
    g_staging_device = dev;
    g_staging_w = bb.Width;
    g_staging_h = bb.Height;
    g_staging_fmt = bb.Format;
    return true;
}

// The actual capture (separate from the SEH-guarded detour so its C++ objects
// are legal). Best-effort: any failure simply skips this frame.
void capture_dx11(IDXGISwapChain* sc) {
    const auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::microseconds>(now - g_last_capture).count()
            < g_frame_interval_us) {
        return;  // throttle to fps
    }
    if (g_control && g_control->stop) return;
    if (g_writer == nullptr) return;

    DXGI_SWAP_CHAIN_DESC desc{};
    if (FAILED(sc->GetDesc(&desc))) return;
    // Only capture the active game, so multiple injected games never fight over
    // the buffer. AMBILIGHT_HOOK_CAPTURE_ALL=1 disables the gate (testing / when
    // a game renders on a non-foreground child window).
    static int fg_gate = -1;
    if (fg_gate == -1) {
        wchar_t v[8] = {0};
        const DWORD n = GetEnvironmentVariableW(L"AMBILIGHT_HOOK_CAPTURE_ALL", v, 8);
        fg_gate = (n > 0 && v[0] == L'1') ? 0 : 1;
    }
    if (fg_gate && desc.OutputWindow != GetForegroundWindow()) return;

    ID3D11Device* dev = nullptr;
    if (FAILED(sc->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&dev))) ||
        dev == nullptr) {
        return;  // not a DX11 swapchain (DX10/DX12 handled elsewhere)
    }
    ID3D11DeviceContext* ctx = nullptr;
    dev->GetImmediateContext(&ctx);

    ID3D11Texture2D* back = nullptr;
    if (ctx != nullptr &&
        SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back))) &&
        back != nullptr) {
        D3D11_TEXTURE2D_DESC td{};
        back->GetDesc(&td);
        if (td.SampleDesc.Count == 1 && ensure_staging(dev, td)) {
            ctx->CopyResource(g_staging, back);
            D3D11_MAPPED_SUBRESOURCE map{};
            if (SUCCEEDED(ctx->Map(g_staging, 0, D3D11_MAP_READ, 0, &map))) {
                if (dxgi_to_bgr(static_cast<const uint8_t*>(map.pData),
                                static_cast<int>(map.RowPitch), td.Width, td.Height,
                                td.Format, g_scratch)) {
                    if (g_writer->write_frame(g_scratch.data(), td.Width, td.Height,
                                              static_cast<uint64_t>(now_us()))) {
                        g_last_capture = now;
                        if (!g_logged_first_frame) {
                            hook_log("DXGI capture live: %ux%u fmt=%d", td.Width, td.Height,
                                     static_cast<int>(td.Format));
                            g_logged_first_frame = true;
                        }
                    } else if (!g_logged_oversize) {
                        hook_log("frame %ux%u exceeds shared buffer; skipping (resize buffer)",
                                 td.Width, td.Height);
                        g_logged_oversize = true;
                    }
                } else if (g_warned_fmt != td.Format) {
                    hook_log("unsupported backbuffer format %d (SDR only); skipping",
                             static_cast<int>(td.Format));
                    g_warned_fmt = td.Format;
                }
                ctx->Unmap(g_staging, 0);
            }
        }
        back->Release();
    }
    if (ctx) ctx->Release();
    if (dev) dev->Release();
}

HRESULT STDMETHODCALLTYPE Present_detour(IDXGISwapChain* self, UINT sync, UINT flags) {
    __try {
        capture_dx11(self);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        // Never let a capture fault break the game's present.
    }
    return g_orig_present(self, sync, flags);
}

HRESULT STDMETHODCALLTYPE ResizeBuffers_detour(IDXGISwapChain* self, UINT count, UINT w,
                                               UINT h, DXGI_FORMAT fmt, UINT flags) {
    release_staging();  // geometry/format changing under us
    return g_orig_resize(self, count, w, h, fmt, flags);
}

// Create a throwaway device+swapchain just to read the DXGI vtable.
IDXGISwapChain* make_dummy_swapchain(HWND hwnd, ID3D11Device** out_dev,
                                     ID3D11DeviceContext** out_ctx) {
    DXGI_SWAP_CHAIN_DESC scd{};
    scd.BufferCount = 1;
    scd.BufferDesc.Width = 8;
    scd.BufferDesc.Height = 8;
    scd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow = hwnd;
    scd.SampleDesc.Count = 1;
    scd.Windowed = TRUE;
    scd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    const D3D_DRIVER_TYPE drivers[] = {D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP};
    for (D3D_DRIVER_TYPE dt : drivers) {
        IDXGISwapChain* sc = nullptr;
        D3D_FEATURE_LEVEL fl{};
        const HRESULT hr = D3D11CreateDeviceAndSwapChain(
            nullptr, dt, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &scd, &sc,
            out_dev, &fl, out_ctx);
        if (SUCCEEDED(hr) && sc != nullptr) return sc;
    }
    return nullptr;
}

}  // namespace

bool install_dxgi_hook(ShmWriter* writer, const HookControl* control) {
    g_writer = writer;
    g_control = control;
    const uint32_t fps = (control && control->fps) ? control->fps : 30;
    g_frame_interval_us = 1000000ll / (fps ? fps : 30);

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"AmbilightDummyDxgi";
    RegisterClassExW(&wc);
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"", WS_OVERLAPPEDWINDOW,
                                0, 0, 8, 8, nullptr, nullptr, wc.hInstance, nullptr);

    ID3D11Device* dev = nullptr;
    ID3D11DeviceContext* ctx = nullptr;
    IDXGISwapChain* sc = make_dummy_swapchain(hwnd, &dev, &ctx);
    if (sc == nullptr) {
        hook_log("DXGI hook: dummy device/swapchain creation failed");
        if (hwnd) DestroyWindow(hwnd);
        return false;
    }

    g_orig_present = reinterpret_cast<Present_t>(
        vmt_hook(sc, kPresentSlot, reinterpret_cast<void*>(&Present_detour)));
    g_orig_resize = reinterpret_cast<ResizeBuffers_t>(
        vmt_hook(sc, kResizeBuffersSlot, reinterpret_cast<void*>(&ResizeBuffers_detour)));

    sc->Release();
    if (ctx) ctx->Release();
    if (dev) dev->Release();
    if (hwnd) DestroyWindow(hwnd);

    if (g_orig_present == nullptr) {
        hook_log("DXGI hook: failed to hook Present");
        return false;
    }
    hook_log("DXGI hook installed (Present + ResizeBuffers), fps=%u", fps);
    return true;
}

}  // namespace ambilight
