// dx11_probe.exe — a minimal DX11 app used to test graphics_hook.dll without a
// real game. It opens a window, creates a swapchain, and every frame clears the
// backbuffer to an alternating known colour (red <-> blue) and Presents. Inject
// graphics_hook.dll into it (capture_host --inject-pid) with
// AMBILIGHT_HOOK_CAPTURE_ALL=1 and the captured frames should match the colour.
//
// Not shipped — a dev/test utility.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>

#include <cstdio>

int main() {
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"AmbilightDx11Probe";
    RegisterClassExW(&wc);

    const UINT W = 640, H = 360;
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"dx11_probe", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                CW_USEDEFAULT, CW_USEDEFAULT, W, H, nullptr, nullptr, wc.hInstance, nullptr);
    if (hwnd == nullptr) { std::fprintf(stderr, "probe: window failed\n"); return 1; }

    DXGI_SWAP_CHAIN_DESC scd{};
    scd.BufferCount = 1;
    scd.BufferDesc.Width = W;
    scd.BufferDesc.Height = H;
    scd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow = hwnd;
    scd.SampleDesc.Count = 1;
    scd.Windowed = TRUE;
    scd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    ID3D11Device* dev = nullptr;
    ID3D11DeviceContext* ctx = nullptr;
    IDXGISwapChain* sc = nullptr;
    D3D_FEATURE_LEVEL fl{};
    HRESULT hr = D3D11CreateDeviceAndSwapChain(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
        &scd, &sc, &dev, &fl, &ctx);
    if (FAILED(hr)) {
        hr = D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_WARP, nullptr, 0, nullptr, 0,
                                           D3D11_SDK_VERSION, &scd, &sc, &dev, &fl, &ctx);
    }
    if (FAILED(hr)) { std::fprintf(stderr, "probe: device failed 0x%08lx\n", hr); return 1; }

    ID3D11Texture2D* back = nullptr;
    sc->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back));
    ID3D11RenderTargetView* rtv = nullptr;
    dev->CreateRenderTargetView(back, nullptr, &rtv);
    if (back) back->Release();

    std::fprintf(stderr, "probe: running %ux%u (pid %lu)\n", W, H, GetCurrentProcessId());
    std::fflush(stderr);

    const float red[4] = {1.f, 0.f, 0.f, 1.f};
    const float blue[4] = {0.f, 0.f, 1.f, 1.f};
    unsigned frame = 0;
    for (;;) {
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) return 0;
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        ctx->OMSetRenderTargets(1, &rtv, nullptr);
        ctx->ClearRenderTargetView(rtv, (frame / 30) % 2 == 0 ? red : blue);
        sc->Present(0, 0);
        ++frame;
        Sleep(8);
    }
}
