// dx12_probe.exe — a minimal Direct3D 12 app to test the DX12 capture path
// without a real game. Each frame it clears the current backbuffer to an
// alternating known colour (red <-> blue) via a command list, executes it on a
// DIRECT queue (so the hook can capture the queue), and Presents.
// Not shipped — a dev/test utility. Falls back to the WARP adapter when no
// hardware DX12 device is available.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>

#include <cstdio>
#include <utility>

static const UINT kW = 640, kH = 360, kBuffers = 2;

int main() {
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"AmbilightD3D12Probe";
    RegisterClassExW(&wc);
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"dx12_probe", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                CW_USEDEFAULT, CW_USEDEFAULT, kW, kH, nullptr, nullptr, wc.hInstance, nullptr);

    IDXGIFactory4* factory = nullptr;
    if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory4), reinterpret_cast<void**>(&factory)))) {
        std::fprintf(stderr, "dx12_probe: factory failed\n"); return 1;
    }

    ID3D12Device* device = nullptr;
    if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, __uuidof(ID3D12Device),
                                 reinterpret_cast<void**>(&device)))) {
        IDXGIAdapter* warp = nullptr;
        factory->EnumWarpAdapter(__uuidof(IDXGIAdapter), reinterpret_cast<void**>(&warp));
        if (warp == nullptr ||
            FAILED(D3D12CreateDevice(warp, D3D_FEATURE_LEVEL_11_0, __uuidof(ID3D12Device),
                                     reinterpret_cast<void**>(&device)))) {
            std::fprintf(stderr, "dx12_probe: no DX12 device (hw or warp)\n"); return 1;
        }
    }

    D3D12_COMMAND_QUEUE_DESC qd{};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    ID3D12CommandQueue* queue = nullptr;
    device->CreateCommandQueue(&qd, __uuidof(ID3D12CommandQueue), reinterpret_cast<void**>(&queue));

    DXGI_SWAP_CHAIN_DESC1 scd{};
    scd.Width = kW;
    scd.Height = kH;
    scd.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.BufferCount = kBuffers;
    scd.SampleDesc.Count = 1;
    scd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
    IDXGISwapChain1* sc1 = nullptr;
    if (FAILED(factory->CreateSwapChainForHwnd(queue, hwnd, &scd, nullptr, nullptr, &sc1))) {
        std::fprintf(stderr, "dx12_probe: swapchain failed\n"); return 1;
    }
    IDXGISwapChain3* sc = nullptr;
    sc1->QueryInterface(__uuidof(IDXGISwapChain3), reinterpret_cast<void**>(&sc));

    D3D12_DESCRIPTOR_HEAP_DESC hd{};
    hd.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
    hd.NumDescriptors = kBuffers;
    ID3D12DescriptorHeap* heap = nullptr;
    device->CreateDescriptorHeap(&hd, __uuidof(ID3D12DescriptorHeap), reinterpret_cast<void**>(&heap));
    const UINT rtv_size = device->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
    ID3D12Resource* rt[kBuffers] = {};
    D3D12_CPU_DESCRIPTOR_HANDLE h = heap->GetCPUDescriptorHandleForHeapStart();
    for (UINT i = 0; i < kBuffers; ++i) {
        sc->GetBuffer(i, __uuidof(ID3D12Resource), reinterpret_cast<void**>(&rt[i]));
        device->CreateRenderTargetView(rt[i], nullptr, h);
        h.ptr += rtv_size;
    }

    ID3D12CommandAllocator* alloc = nullptr;
    device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                   __uuidof(ID3D12CommandAllocator), reinterpret_cast<void**>(&alloc));
    ID3D12GraphicsCommandList* list = nullptr;
    device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, alloc, nullptr,
                              __uuidof(ID3D12GraphicsCommandList), reinterpret_cast<void**>(&list));
    list->Close();

    ID3D12Fence* fence = nullptr;
    device->CreateFence(0, D3D12_FENCE_FLAG_NONE, __uuidof(ID3D12Fence), reinterpret_cast<void**>(&fence));
    HANDLE ev = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    UINT64 fence_val = 0;

    std::fprintf(stderr, "dx12_probe: running %ux%u (pid %lu)\n", kW, kH, GetCurrentProcessId());
    std::fflush(stderr);

    unsigned frame = 0;
    for (;;) {
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) return 0;
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        const UINT idx = sc->GetCurrentBackBufferIndex();
        alloc->Reset();
        list->Reset(alloc, nullptr);

        D3D12_RESOURCE_BARRIER b{};
        b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        b.Transition.pResource = rt[idx];
        b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        b.Transition.StateBefore = D3D12_RESOURCE_STATE_PRESENT;
        b.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;
        list->ResourceBarrier(1, &b);

        D3D12_CPU_DESCRIPTOR_HANDLE rtv = heap->GetCPUDescriptorHandleForHeapStart();
        rtv.ptr += static_cast<SIZE_T>(idx) * rtv_size;
        const float red[4] = {1.f, 0.f, 0.f, 1.f};
        const float blue[4] = {0.f, 0.f, 1.f, 1.f};
        list->ClearRenderTargetView(rtv, (frame / 30) % 2 == 0 ? red : blue, 0, nullptr);

        std::swap(b.Transition.StateBefore, b.Transition.StateAfter);
        list->ResourceBarrier(1, &b);
        list->Close();

        ID3D12CommandList* lists[] = {list};
        queue->ExecuteCommandLists(1, lists);
        sc->Present(0, 0);

        const UINT64 v = ++fence_val;
        queue->Signal(fence, v);
        if (fence->GetCompletedValue() < v) {
            fence->SetEventOnCompletion(v, ev);
            WaitForSingleObject(ev, INFINITE);
        }
        ++frame;
        Sleep(8);
    }
}
