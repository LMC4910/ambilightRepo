// dllmain.cpp — entry point for graphics_hook.dll.
//
// Injected into a target game by capture_host.exe. On attach it spawns an init
// thread (no real work inside the loader lock) that opens the control mapping to
// learn the frame-buffer name + fps, attaches the shared-memory writer, and
// installs the Present hooks. The writer and control mapping are kept alive for
// the process lifetime because the installed hooks reference them.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <string>

#include "shm_writer.h"
#include "hook_control.h"
#include "hook_dxgi.h"
#include "hook_d3d9.h"
#include "hook_vulkan.h"
#include "hooklog.h"

#include <MinHook.h>

namespace {

HMODULE g_self = nullptr;

// Process-lifetime state referenced by the installed hooks.
ambilight::ShmWriter g_writer;
const ambilight::HookControl* g_control = nullptr;
HANDLE g_ctrl_map = nullptr;

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

    g_ctrl_map = OpenFileMappingW(FILE_MAP_READ, FALSE, AMBILIGHT_HOOK_CONTROL_NAME);
    if (g_ctrl_map == nullptr) {
        ambilight::hook_log("control mapping not found (err %lu)", GetLastError());
        return 0;
    }
    g_control = reinterpret_cast<const ambilight::HookControl*>(
        MapViewOfFile(g_ctrl_map, FILE_MAP_READ, 0, 0, sizeof(ambilight::HookControl)));
    if (g_control == nullptr) {
        ambilight::hook_log("MapViewOfFile(control) failed (err %lu)", GetLastError());
        CloseHandle(g_ctrl_map);
        g_ctrl_map = nullptr;
        return 0;
    }
    if (g_control->magic != ambilight::HOOK_CONTROL_MAGIC ||
        g_control->version != ambilight::HOOK_CONTROL_VERSION) {
        ambilight::hook_log("control mapping invalid (magic/version)");
        return 0;
    }
    ambilight::hook_log("control ok: shm=%s fps=%u", g_control->shm_name, g_control->fps);

    // Attach the shared-memory writer (Python-owned frame ring buffer).
    wchar_t shm_w[ambilight::HOOK_SHM_NAME_MAX] = {0};
    MultiByteToWideChar(CP_UTF8, 0, g_control->shm_name, -1, shm_w, ambilight::HOOK_SHM_NAME_MAX);
    if (!g_writer.open(shm_w)) {
        ambilight::hook_log("ShmWriter.open failed: %s", g_writer.last_error().c_str());
        return 0;
    }
    ambilight::hook_log("shared buffer attached: %ux%u", g_writer.max_width(), g_writer.max_height());

    // Install only the hooks the target actually needs, based on which Direct3D
    // runtimes it has loaded. The Present detours start publishing frames once the
    // game's window is foreground.
    const bool has_dxgi = GetModuleHandleW(L"d3d11.dll") || GetModuleHandleW(L"d3d12.dll") ||
                          GetModuleHandleW(L"d3d10.dll");
    const bool has_d3d9 = GetModuleHandleW(L"d3d9.dll") != nullptr;
    const bool has_vulkan = GetModuleHandleW(L"vulkan-1.dll") != nullptr;
    if (!has_dxgi && !has_d3d9 && !has_vulkan) {
        ambilight::hook_log("no Direct3D/Vulkan runtime detected in this process; no hooks installed");
        return 0;
    }

    // MinHook backs the inline hooks (D3D9 / D3D12). DXGI uses VMT and needs no
    // init, but initializing here is harmless and centralizes it.
    const MH_STATUS mh = MH_Initialize();
    if (mh != MH_OK && mh != MH_ERROR_ALREADY_INITIALIZED) {
        ambilight::hook_log("MH_Initialize failed (%d)", mh);
    }

    if (has_dxgi) ambilight::install_dxgi_hook(&g_writer, g_control);
    if (has_d3d9) ambilight::install_d3d9_hook(&g_writer, g_control);
    if (has_vulkan) ambilight::install_vulkan_hook(&g_writer, g_control);
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
