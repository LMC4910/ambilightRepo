// dx9_probe.exe — a minimal Direct3D 9 app to test the D3D9 hook without a real
// game. Clears the backbuffer to an alternating known colour (red <-> blue) and
// Presents each frame. Not shipped — a dev/test utility.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <d3d9.h>

#include <cstdio>

int main() {
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"AmbilightD3D9Probe";
    RegisterClassExW(&wc);

    const UINT W = 640, H = 360;
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"dx9_probe", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                CW_USEDEFAULT, CW_USEDEFAULT, W, H, nullptr, nullptr, wc.hInstance, nullptr);
    if (hwnd == nullptr) { std::fprintf(stderr, "dx9_probe: window failed\n"); return 1; }

    IDirect3D9* d3d = Direct3DCreate9(D3D_SDK_VERSION);
    if (d3d == nullptr) { std::fprintf(stderr, "dx9_probe: Direct3DCreate9 failed\n"); return 1; }

    D3DPRESENT_PARAMETERS pp{};
    pp.Windowed = TRUE;
    pp.SwapEffect = D3DSWAPEFFECT_DISCARD;
    pp.BackBufferFormat = D3DFMT_X8R8G8B8;
    pp.BackBufferWidth = W;
    pp.BackBufferHeight = H;
    pp.hDeviceWindow = hwnd;

    IDirect3DDevice9* dev = nullptr;
    HRESULT hr = d3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, hwnd,
                                   D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &dev);
    if (FAILED(hr)) {
        hr = d3d->CreateDevice(D3DADAPTER_DEFAULT, D3DDEVTYPE_REF, hwnd,
                               D3DCREATE_SOFTWARE_VERTEXPROCESSING, &pp, &dev);
    }
    if (FAILED(hr) || dev == nullptr) { std::fprintf(stderr, "dx9_probe: CreateDevice 0x%08lx\n", hr); return 1; }

    std::fprintf(stderr, "dx9_probe: running %ux%u (pid %lu)\n", W, H, GetCurrentProcessId());
    std::fflush(stderr);

    unsigned frame = 0;
    for (;;) {
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) return 0;
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        const D3DCOLOR color = (frame / 30) % 2 == 0 ? D3DCOLOR_XRGB(255, 0, 0)
                                                     : D3DCOLOR_XRGB(0, 0, 255);
        dev->Clear(0, nullptr, D3DCLEAR_TARGET, color, 1.0f, 0);
        dev->BeginScene();
        dev->EndScene();
        dev->Present(nullptr, nullptr, nullptr, nullptr);
        ++frame;
        Sleep(8);
    }
}
