// dllmain.cpp — entry point for graphics_hook.dll.
//
// Injected into a target game by capture_host.exe. On attach it spawns an init
// thread (no real work inside the loader lock) that opens the control mapping to
// learn the frame-buffer name + fps, then (in later commits) attaches the
// shared-memory writer and installs the Present hooks.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <string>

#include "hook_control.h"
#include "hooklog.h"

namespace {

HMODULE g_self = nullptr;

std::string self_exe() {
    wchar_t buf[MAX_PATH];
    const DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH);
    std::wstring p(buf, n);
    const size_t slash = p.find_last_of(L"\\/");
    const std::wstring base = (slash == std::wstring::npos) ? p : p.substr(slash + 1);
    char out[MAX_PATH] = {0};
    WideCharToMultiByte(CP_UTF8, 0, base.c_str(), -1, out, sizeof(out), nullptr, nullptr);
    return out;
}

DWORD WINAPI InitThread(LPVOID) {
    ambilight::hook_log("attached to %s (pid %lu)", self_exe().c_str(), GetCurrentProcessId());

    HANDLE map = OpenFileMappingW(FILE_MAP_READ, FALSE, AMBILIGHT_HOOK_CONTROL_NAME);
    if (map == nullptr) {
        ambilight::hook_log("control mapping not found (err %lu)", GetLastError());
        return 0;
    }
    auto* ctrl = reinterpret_cast<const ambilight::HookControl*>(
        MapViewOfFile(map, FILE_MAP_READ, 0, 0, sizeof(ambilight::HookControl)));
    if (ctrl == nullptr) {
        ambilight::hook_log("MapViewOfFile(control) failed (err %lu)", GetLastError());
        CloseHandle(map);
        return 0;
    }
    if (ctrl->magic != ambilight::HOOK_CONTROL_MAGIC ||
        ctrl->version != ambilight::HOOK_CONTROL_VERSION) {
        ambilight::hook_log("control mapping invalid (magic/version)");
        UnmapViewOfFile(ctrl);
        CloseHandle(map);
        return 0;
    }

    ambilight::hook_log("control ok: shm=%s fps=%u", ctrl->shm_name, ctrl->fps);
    // Next commits: ShmWriter.open(ctrl->shm_name); install VMT hooks on Present
    // (DXGI for DX10/11/12, D3D9 separately); capture backbuffer -> BGR -> SHM.

    UnmapViewOfFile(ctrl);
    CloseHandle(map);
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
