// dllmain.cpp — entry point for graphics_hook.dll.
//
// Injected into a target game by capture_host.exe. On attach it spawns an init
// thread (no real work inside the loader lock) that will open the control
// mapping, attach the shared-memory writer, and install the Present hooks.
//
// Phase-2 skeleton: the init thread is wired up incrementally (control mapping →
// VMT hooks → per-API capture) in the following commits.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace {

HMODULE g_self = nullptr;

DWORD WINAPI InitThread(LPVOID) {
    // Subsequent commits: open AMBILIGHT_HOOK_CONTROL_NAME, ShmWriter.open(),
    // install VMT hooks on Present/ResizeBuffers (+ D3D9 / D3D12 paths).
    return 0;
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID /*reserved*/) {
    switch (reason) {
        case DLL_PROCESS_ATTACH:
            g_self = module;
            DisableThreadLibraryCalls(module);
            if (HANDLE t = CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr)) {
                CloseHandle(t);
            }
            break;
        default:
            break;
    }
    return TRUE;
}
