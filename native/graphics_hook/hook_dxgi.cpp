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
#include <d3d10.h>
#include <d3d12.h>
#include <dxgi.h>
#include <dxgi1_4.h>

#include <chrono>
#include <utility>
#include <vector>

#include "hook_dxgi.h"
#include "shm_writer.h"
#include "hook_control.h"
#include "vmt_hook.h"
#include "capture_util.h"
#include "hooklog.h"

#include <MinHook.h>

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

// --- DX12 capture state (command-queue path) ---
using ExecuteCommandLists_t =
    void(STDMETHODCALLTYPE*)(ID3D12CommandQueue*, UINT, ID3D12CommandList* const*);
constexpr unsigned kExecuteCommandListsSlot = 10;
ExecuteCommandLists_t g_orig_execute = nullptr;
ID3D12CommandQueue* g_d12_queue = nullptr;   // a captured DIRECT queue (AddRef'd)
ID3D12Device* g_d12_device = nullptr;        // owner of our cached copy resources
ID3D12CommandAllocator* g_d12_alloc = nullptr;
ID3D12GraphicsCommandList* g_d12_list = nullptr;
ID3D12Fence* g_d12_fence = nullptr;
HANDLE g_d12_event = nullptr;
UINT64 g_d12_fence_val = 0;
ID3D12Resource* g_d12_readback = nullptr;
UINT64 g_d12_readback_size = 0;
bool g_logged_no_queue = false;

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

// Convert a mapped BGRA/RGBA surface to BGR and publish it. Returns true on a
// successful write (and stamps g_last_capture). Shared by the DX11 and DX10 paths.
bool publish_bgr(const uint8_t* data, int pitch, UINT w, UINT h, DXGI_FORMAT fmt,
                 const std::chrono::steady_clock::time_point& now) {
    if (!dxgi_to_bgr(data, pitch, w, h, fmt, g_scratch)) {
        if (g_warned_fmt != fmt) {
            hook_log("unsupported backbuffer format %d (SDR only); skipping", static_cast<int>(fmt));
            g_warned_fmt = fmt;
        }
        return false;
    }
    if (!g_writer->write_frame(g_scratch.data(), w, h, static_cast<uint64_t>(now_us()))) {
        if (!g_logged_oversize) {
            hook_log("frame %ux%u exceeds shared buffer; skipping (resize buffer)", w, h);
            g_logged_oversize = true;
        }
        return false;
    }
    g_last_capture = now;
    if (!g_logged_first_frame) {
        hook_log("DXGI capture live: %ux%u fmt=%d", w, h, static_cast<int>(fmt));
        g_logged_first_frame = true;
    }
    return true;
}

void capture_d11(IDXGISwapChain* sc, ID3D11Device* dev,
                 const std::chrono::steady_clock::time_point& now) {
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
                publish_bgr(static_cast<const uint8_t*>(map.pData), static_cast<int>(map.RowPitch),
                            td.Width, td.Height, td.Format, now);
                ctx->Unmap(g_staging, 0);
            }
        }
        back->Release();
    }
    if (ctx) ctx->Release();
}

// DX10 is rare today, so this uses a per-frame staging texture (no cache) to keep
// the code small. Uses only d3d10.h interfaces (no d3d10.lib export is called),
// so the DLL gains no forced d3d10.dll dependency.
void capture_d10(IDXGISwapChain* sc, ID3D10Device* dev,
                 const std::chrono::steady_clock::time_point& now) {
    ID3D10Texture2D* back = nullptr;
    if (SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D10Texture2D), reinterpret_cast<void**>(&back))) &&
        back != nullptr) {
        D3D10_TEXTURE2D_DESC td{};
        back->GetDesc(&td);
        if (td.SampleDesc.Count == 1) {
            D3D10_TEXTURE2D_DESC sd{};
            sd.Width = td.Width;
            sd.Height = td.Height;
            sd.MipLevels = 1;
            sd.ArraySize = 1;
            sd.Format = td.Format;
            sd.SampleDesc.Count = 1;
            sd.Usage = D3D10_USAGE_STAGING;
            sd.CPUAccessFlags = D3D10_CPU_ACCESS_READ;
            ID3D10Texture2D* staging = nullptr;
            if (SUCCEEDED(dev->CreateTexture2D(&sd, nullptr, &staging)) && staging != nullptr) {
                dev->CopyResource(staging, back);
                D3D10_MAPPED_TEXTURE2D map{};
                if (SUCCEEDED(staging->Map(0, D3D10_MAP_READ, 0, &map))) {
                    publish_bgr(static_cast<const uint8_t*>(map.pData), static_cast<int>(map.RowPitch),
                                td.Width, td.Height, td.Format, now);
                    staging->Unmap(0);
                }
                staging->Release();
            }
        }
        back->Release();
    }
}

// --- DX12 ---------------------------------------------------------------
// DX12 needs a command queue to copy the backbuffer. The swapchain is created
// with the queue (not the device), so we capture a DIRECT queue by hooking
// ID3D12CommandQueue::ExecuteCommandLists.

void STDMETHODCALLTYPE Execute_detour(ID3D12CommandQueue* self, UINT num,
                                      ID3D12CommandList* const* lists) {
    if (g_d12_queue == nullptr && self != nullptr) {
        const D3D12_COMMAND_QUEUE_DESC d = self->GetDesc();
        if (d.Type == D3D12_COMMAND_LIST_TYPE_DIRECT) {
            self->AddRef();
            g_d12_queue = self;
            hook_log("captured D3D12 direct command queue");
        }
    }
    g_orig_execute(self, num, lists);
}

void release_d12_resources() {
    if (g_d12_readback) { g_d12_readback->Release(); g_d12_readback = nullptr; }
    if (g_d12_list) { g_d12_list->Release(); g_d12_list = nullptr; }
    if (g_d12_alloc) { g_d12_alloc->Release(); g_d12_alloc = nullptr; }
    if (g_d12_fence) { g_d12_fence->Release(); g_d12_fence = nullptr; }
    if (g_d12_event) { CloseHandle(g_d12_event); g_d12_event = nullptr; }
    g_d12_device = nullptr;
    g_d12_readback_size = 0;
    g_d12_fence_val = 0;
}

bool ensure_d12_resources(ID3D12Device* dev, UINT64 readback_size) {
    if (g_d12_device == dev && g_d12_alloc && g_d12_list && g_d12_fence &&
        g_d12_readback && g_d12_readback_size >= readback_size) {
        return true;
    }
    if (g_d12_device != dev) release_d12_resources();

    if (g_d12_alloc == nullptr &&
        FAILED(dev->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                           __uuidof(ID3D12CommandAllocator),
                                           reinterpret_cast<void**>(&g_d12_alloc)))) {
        return false;
    }
    if (g_d12_list == nullptr) {
        if (FAILED(dev->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, g_d12_alloc, nullptr,
                                          __uuidof(ID3D12GraphicsCommandList),
                                          reinterpret_cast<void**>(&g_d12_list)))) {
            return false;
        }
        g_d12_list->Close();  // start closed; we Reset() each frame
    }
    if (g_d12_fence == nullptr) {
        if (FAILED(dev->CreateFence(0, D3D12_FENCE_FLAG_NONE, __uuidof(ID3D12Fence),
                                    reinterpret_cast<void**>(&g_d12_fence)))) {
            return false;
        }
        g_d12_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    }
    if (g_d12_readback == nullptr || g_d12_readback_size < readback_size) {
        if (g_d12_readback) { g_d12_readback->Release(); g_d12_readback = nullptr; }
        D3D12_HEAP_PROPERTIES heap{};
        heap.Type = D3D12_HEAP_TYPE_READBACK;
        D3D12_RESOURCE_DESC rd{};
        rd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        rd.Width = readback_size;
        rd.Height = 1;
        rd.DepthOrArraySize = 1;
        rd.MipLevels = 1;
        rd.Format = DXGI_FORMAT_UNKNOWN;
        rd.SampleDesc.Count = 1;
        rd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        if (FAILED(dev->CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &rd,
                                                D3D12_RESOURCE_STATE_COPY_DEST, nullptr,
                                                __uuidof(ID3D12Resource),
                                                reinterpret_cast<void**>(&g_d12_readback)))) {
            return false;
        }
        g_d12_readback_size = readback_size;
    }
    g_d12_device = dev;
    return true;
}

void capture_d12(IDXGISwapChain* sc, ID3D12Device* dev,
                 const std::chrono::steady_clock::time_point& now) {
    if (g_d12_queue == nullptr) {
        if (!g_logged_no_queue) {
            hook_log("DX12: waiting for a command queue (ExecuteCommandLists)");
            g_logged_no_queue = true;
        }
        return;
    }

    IDXGISwapChain3* sc3 = nullptr;
    if (FAILED(sc->QueryInterface(__uuidof(IDXGISwapChain3), reinterpret_cast<void**>(&sc3))) ||
        sc3 == nullptr) {
        return;
    }
    const UINT idx = sc3->GetCurrentBackBufferIndex();
    sc3->Release();

    ID3D12Resource* back = nullptr;
    if (FAILED(sc->GetBuffer(idx, __uuidof(ID3D12Resource), reinterpret_cast<void**>(&back))) ||
        back == nullptr) {
        return;
    }
    const D3D12_RESOURCE_DESC rd = back->GetDesc();

    D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp{};
    UINT rows = 0;
    UINT64 row_bytes = 0, total = 0;
    dev->GetCopyableFootprints(&rd, 0, 1, 0, &fp, &rows, &row_bytes, &total);

    if (ensure_d12_resources(dev, total)) {
        g_d12_alloc->Reset();
        g_d12_list->Reset(g_d12_alloc, nullptr);

        D3D12_RESOURCE_BARRIER b{};
        b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        b.Transition.pResource = back;
        b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        b.Transition.StateBefore = D3D12_RESOURCE_STATE_PRESENT;
        b.Transition.StateAfter = D3D12_RESOURCE_STATE_COPY_SOURCE;
        g_d12_list->ResourceBarrier(1, &b);

        D3D12_TEXTURE_COPY_LOCATION dst{};
        dst.pResource = g_d12_readback;
        dst.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
        dst.PlacedFootprint = fp;
        D3D12_TEXTURE_COPY_LOCATION src{};
        src.pResource = back;
        src.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
        src.SubresourceIndex = 0;
        g_d12_list->CopyTextureRegion(&dst, 0, 0, 0, &src, nullptr);

        std::swap(b.Transition.StateBefore, b.Transition.StateAfter);  // back to PRESENT
        g_d12_list->ResourceBarrier(1, &b);
        g_d12_list->Close();

        ID3D12CommandList* lists[] = {g_d12_list};
        g_orig_execute(g_d12_queue, 1, lists);  // original, to avoid re-entering our detour

        const UINT64 v = ++g_d12_fence_val;
        if (SUCCEEDED(g_d12_queue->Signal(g_d12_fence, v))) {
            if (g_d12_fence->GetCompletedValue() < v && g_d12_event != nullptr) {
                g_d12_fence->SetEventOnCompletion(v, g_d12_event);
                WaitForSingleObject(g_d12_event, 1000);
            }
            void* mapped = nullptr;
            D3D12_RANGE read_range{0, static_cast<SIZE_T>(total)};
            if (SUCCEEDED(g_d12_readback->Map(0, &read_range, &mapped)) && mapped) {
                publish_bgr(static_cast<const uint8_t*>(mapped),
                            static_cast<int>(fp.Footprint.RowPitch),
                            static_cast<UINT>(rd.Width), rd.Height, rd.Format, now);
                D3D12_RANGE no_write{0, 0};
                g_d12_readback->Unmap(0, &no_write);
            }
        }
    }
    back->Release();
}

bool install_d3d12_queue_hook() {
    HMODULE d3d12 = GetModuleHandleW(L"d3d12.dll");
    if (d3d12 == nullptr) return false;
    using D3D12CreateDevice_t = HRESULT(WINAPI*)(IUnknown*, D3D_FEATURE_LEVEL, REFIID, void**);
    auto create = reinterpret_cast<D3D12CreateDevice_t>(GetProcAddress(d3d12, "D3D12CreateDevice"));
    if (create == nullptr) return false;

    ID3D12Device* dev = nullptr;
    if (FAILED(create(nullptr, D3D_FEATURE_LEVEL_11_0, __uuidof(ID3D12Device),
                      reinterpret_cast<void**>(&dev))) || dev == nullptr) {
        hook_log("DX12: dummy device creation failed (no DX12 adapter?)");
        return false;
    }
    D3D12_COMMAND_QUEUE_DESC qd{};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    ID3D12CommandQueue* q = nullptr;
    bool ok = false;
    if (SUCCEEDED(dev->CreateCommandQueue(&qd, __uuidof(ID3D12CommandQueue),
                                          reinterpret_cast<void**>(&q))) && q != nullptr) {
        void** vt = *reinterpret_cast<void***>(q);
        void* el_addr = vt[kExecuteCommandListsSlot];
        q->Release();
        if (MH_CreateHook(el_addr, reinterpret_cast<LPVOID>(&Execute_detour),
                          reinterpret_cast<LPVOID*>(&g_orig_execute)) == MH_OK &&
            MH_EnableHook(el_addr) == MH_OK) {
            ok = true;
        }
    }
    dev->Release();
    hook_log(ok ? "DX12 queue hook installed (ExecuteCommandLists)"
               : "DX12 queue hook failed");
    return ok;
}

// The actual capture (separate from the SEH-guarded detour so its C++ objects
// are legal). Best-effort: any failure simply skips this frame.
void capture_dxgi(IDXGISwapChain* sc) {
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

    // Branch on the swapchain's device type. (DX12 is handled by a separate path.)
    ID3D11Device* d11 = nullptr;
    if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D11Device), reinterpret_cast<void**>(&d11))) &&
        d11 != nullptr) {
        capture_d11(sc, d11, now);
        d11->Release();
        return;
    }
    ID3D10Device* d10 = nullptr;
    if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D10Device), reinterpret_cast<void**>(&d10))) &&
        d10 != nullptr) {
        capture_d10(sc, d10, now);
        d10->Release();
        return;
    }
    ID3D12Device* d12 = nullptr;
    if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D12Device), reinterpret_cast<void**>(&d12))) &&
        d12 != nullptr) {
        capture_d12(sc, d12, now);
        d12->Release();
        return;
    }
}

HRESULT STDMETHODCALLTYPE Present_detour(IDXGISwapChain* self, UINT sync, UINT flags) {
    __try {
        capture_dxgi(self);
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

// Create a throwaway device+swapchain just to read the DXGI vtable. D3D11 is
// resolved dynamically (and loaded on demand) so graphics_hook.dll has no
// link-time DirectX dependency — injecting into any game stays clean.
using D3D11CreateDeviceAndSwapChain_t = HRESULT(WINAPI*)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT,
    const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**, ID3D11Device**, D3D_FEATURE_LEVEL*,
    ID3D11DeviceContext**);

IDXGISwapChain* make_dummy_swapchain(HWND hwnd, ID3D11Device** out_dev,
                                     ID3D11DeviceContext** out_ctx) {
    HMODULE d3d11 = GetModuleHandleW(L"d3d11.dll");
    if (d3d11 == nullptr) d3d11 = LoadLibraryW(L"d3d11.dll");
    if (d3d11 == nullptr) return nullptr;
    auto create = reinterpret_cast<D3D11CreateDeviceAndSwapChain_t>(
        GetProcAddress(d3d11, "D3D11CreateDeviceAndSwapChain"));
    if (create == nullptr) return nullptr;

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
        const HRESULT hr = create(nullptr, dt, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
                                  &scd, &sc, out_dev, &fl, out_ctx);
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

    // For DX12 games we also need a command queue to copy the backbuffer.
    if (GetModuleHandleW(L"d3d12.dll") != nullptr) {
        install_d3d12_queue_hook();
    }
    return true;
}

}  // namespace ambilight
