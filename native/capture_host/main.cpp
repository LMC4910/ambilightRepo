// capture_host.exe — the native side of the hook capture transport.
//
// Two modes:
//   --mode fake : write an animated BGR rainbow into the Python-owned shared
//                 mapping (proves the transport; used by the tests).
//   --mode hook : auto-detect the foreground fullscreen Direct3D game, inject
//                 graphics_hook.dll into it, and let the DLL publish real frames
//                 through the SAME shared mapping. capture_host itself does NOT
//                 touch the frame buffer in hook mode — it only injects and hands
//                 the DLL the buffer name via the control mapping.
//
// Lifecycle: exits cleanly when stdin reaches EOF (Python closed the pipe / died)
// or when --parent-pid is supplied and that process exits, so it never lingers
// as an orphan after Python goes away.
//
// Usage:
//   capture_host.exe --shm-name <NAME> [--fps 30] --mode fake [--parent-pid N]
//   capture_host.exe --shm-name <NAME> [--fps 30] --mode hook [--target auto|exe] [--parent-pid N]

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <thread>
#include <vector>

#include "shm_protocol.h"
#include "shm_writer.h"
#include "hook_control.h"
#include "inject.h"
#include "detect.h"

namespace {

std::atomic<bool> g_running{true};

BOOL WINAPI ConsoleHandler(DWORD) {
    g_running.store(false);
    return TRUE;
}

uint64_t now_us() {
    using namespace std::chrono;
    return static_cast<uint64_t>(
        duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count());
}

void stdin_watch_thread() {
    HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
    char buf[64];
    DWORD got = 0;
    for (;;) {
        if (in == nullptr || in == INVALID_HANDLE_VALUE) return;  // no stdin; rely on parent-pid
        if (!ReadFile(in, buf, sizeof(buf), &got, nullptr) || got == 0) {
            g_running.store(false);
            return;
        }
    }
}

// HSV (h in [0,1), s=v=1) -> BGR triplet. Used to paint the rainbow.
void hue_to_bgr(double h, uint8_t& b, uint8_t& g, uint8_t& r) {
    h = h - std::floor(h);
    const double hp = h * 6.0;
    const int i = static_cast<int>(hp) % 6;
    const double f = hp - std::floor(hp);
    const uint8_t v = 255;
    const uint8_t p = 0;
    const uint8_t q = static_cast<uint8_t>(255.0 * (1.0 - f));
    const uint8_t t = static_cast<uint8_t>(255.0 * f);
    switch (i) {
        case 0: r = v; g = t; b = p; break;
        case 1: r = q; g = v; b = p; break;
        case 2: r = p; g = v; b = t; break;
        case 3: r = p; g = q; b = v; break;
        case 4: r = t; g = p; b = v; break;
        default: r = v; g = p; b = q; break;
    }
}

std::wstring arg_value(int argc, wchar_t** argv, const std::wstring& key) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (key == argv[i]) return argv[i + 1];
    }
    return L"";
}

bool parent_alive(HANDLE parent) {
    if (parent == nullptr) return true;  // no parent to watch
    return WaitForSingleObject(parent, 0) == WAIT_TIMEOUT;
}

void logline(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::fprintf(stderr, "capture_host: ");
    std::vfprintf(stderr, fmt, ap);
    std::fprintf(stderr, "\n");
    std::fflush(stderr);
    va_end(ap);
}

std::wstring exe_dir() {
    wchar_t buf[MAX_PATH];
    const DWORD n = GetModuleFileNameW(nullptr, buf, MAX_PATH);
    std::wstring p(buf, n);
    const size_t slash = p.find_last_of(L"\\/");
    return slash == std::wstring::npos ? L"." : p.substr(0, slash);
}

// ---------------------------------------------------------------------------
// Fake mode (Phase 1 transport source)
// ---------------------------------------------------------------------------

int run_fake_mode(const std::wstring& shm_name, int fps, HANDLE parent) {
    ambilight::ShmWriter writer;
    if (!writer.open(shm_name)) {
        logline("%s", writer.last_error().c_str());
        return 1;
    }
    const uint32_t w = writer.max_width();
    const uint32_t h = writer.max_height();
    logline("attached %ux%u @ %d fps (fake)", w, h, fps);

    std::vector<uint8_t> row(static_cast<size_t>(w) * 3u);
    std::vector<uint8_t> frame(static_cast<size_t>(w) * static_cast<size_t>(h) * 3u);
    const auto frame_interval = std::chrono::microseconds(1000000 / fps);
    uint64_t tick = 0;
    auto next = std::chrono::steady_clock::now();

    while (g_running.load() && parent_alive(parent)) {
        const double phase = static_cast<double>(tick) * 0.01;
        for (uint32_t x = 0; x < w; ++x) {
            uint8_t b, g, r;
            hue_to_bgr(static_cast<double>(x) / static_cast<double>(w) + phase, b, g, r);
            row[x * 3 + 0] = b;
            row[x * 3 + 1] = g;
            row[x * 3 + 2] = r;
        }
        for (uint32_t y = 0; y < h; ++y) {
            std::memcpy(frame.data() + static_cast<size_t>(y) * w * 3u, row.data(), row.size());
        }
        writer.write_frame(frame.data(), w, h, now_us());
        ++tick;
        next += frame_interval;
        std::this_thread::sleep_until(next);
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Hook mode (Phase 2 real game capture: detect + inject)
// ---------------------------------------------------------------------------

// Inject graphics_hook.dll into *pid* unless already done; updates *state*
// (-1 = injected, >=0 = failed attempts) and logs the outcome. *forced* skips
// the "already logged" suppression nuance — it is an explicit override.
void try_inject(DWORD pid, const std::wstring& dll, const char* exe_utf8,
                std::map<DWORD, int>& state) {
    auto it = state.find(pid);
    const int attempts = (it == state.end()) ? 0 : it->second;
    if (attempts == -1) return;  // already injected
    if (ambilight::is_wow64_process(pid)) {
        logline("skip %s (pid %lu): 32-bit target not supported", exe_utf8, pid);
        state[pid] = -1;
        return;
    }
    if (attempts >= 3) return;  // gave up
    const ambilight::InjectResult r = ambilight::inject_dll(pid, dll);
    if (r.status == ambilight::InjectStatus::Ok) {
        logline("injected into %s (pid %lu)", exe_utf8, pid);
        state[pid] = -1;
    } else {
        logline("inject %s (pid %lu) failed: %s (err %lu)", exe_utf8, pid,
                ambilight::inject_status_str(r.status), r.win32_error);
        state[pid] = attempts + 1;
    }
}

int run_hook_mode(const std::wstring& shm_name, int fps,
                  const std::wstring& target, DWORD force_pid, HANDLE parent) {
    char target_utf8[256] = {0};
    WideCharToMultiByte(CP_UTF8, 0, target.c_str(), -1, target_utf8, sizeof(target_utf8), nullptr, nullptr);
    logline("hook mode, target=%s", target_utf8);

    logline("SeDebugPrivilege %s", ambilight::enable_debug_privilege() ? "enabled" : "unavailable");

    // Control mapping: hands the injected DLL the frame-buffer name + fps + stop.
    HANDLE map = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
                                    sizeof(ambilight::HookControl), AMBILIGHT_HOOK_CONTROL_NAME);
    if (map == nullptr) {
        logline("CreateFileMapping(control) failed: %lu", GetLastError());
        return 1;
    }
    auto* ctrl = reinterpret_cast<ambilight::HookControl*>(
        MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(ambilight::HookControl)));
    if (ctrl == nullptr) {
        logline("MapViewOfFile(control) failed: %lu", GetLastError());
        CloseHandle(map);
        return 1;
    }
    ZeroMemory(ctrl, sizeof(*ctrl));
    ctrl->magic = ambilight::HOOK_CONTROL_MAGIC;
    ctrl->version = ambilight::HOOK_CONTROL_VERSION;
    ctrl->fps = static_cast<uint32_t>(fps);
    ctrl->stop = 0;
    WideCharToMultiByte(CP_UTF8, 0, shm_name.c_str(), -1, ctrl->shm_name,
                        ambilight::HOOK_SHM_NAME_MAX, nullptr, nullptr);

    const std::wstring dll = exe_dir() + L"\\graphics_hook.dll";
    char dll_utf8[MAX_PATH] = {0};
    WideCharToMultiByte(CP_UTF8, 0, dll.c_str(), -1, dll_utf8, sizeof(dll_utf8), nullptr, nullptr);
    if (GetFileAttributesW(dll.c_str()) == INVALID_FILE_ATTRIBUTES) {
        logline("WARNING: graphics_hook.dll not found at %s", dll_utf8);
    } else {
        logline("hook dll: %s", dll_utf8);
    }

    // -1 = injected OK (skip); >=0 = failed-attempt count. Pruned when the pid dies.
    std::map<DWORD, int> state;
    std::string last_reason;

    while (g_running.load() && parent_alive(parent)) {
        // Prune exited games so a relaunched title (new pid) gets re-injected.
        for (auto it = state.begin(); it != state.end();) {
            if (!ambilight::process_alive(it->first)) it = state.erase(it);
            else ++it;
        }

        // Explicit override: force-inject a specific pid (manual testing / when
        // auto-detection misses a game). Bypasses the fullscreen/game gates.
        if (force_pid != 0 && ambilight::process_alive(force_pid)) {
            try_inject(force_pid, dll, "(forced)", state);
        }

        ambilight::GameTarget gt;
        std::string reason;
        if (ambilight::detect_foreground_game(target, gt, reason)) {
            char exe_utf8[MAX_PATH] = {0};
            WideCharToMultiByte(CP_UTF8, 0, gt.exe.c_str(), -1, exe_utf8, sizeof(exe_utf8), nullptr, nullptr);
            try_inject(gt.pid, dll, exe_utf8, state);
        } else if (reason != last_reason) {
            logline("skip: %s", reason.c_str());
            last_reason = reason;
        }

        Sleep(400);
    }

    ctrl->stop = 1;  // tell injected DLLs to stop writing
    Sleep(100);
    UnmapViewOfFile(ctrl);
    CloseHandle(map);
    return 0;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    const std::wstring shm_name = arg_value(argc, argv, L"--shm-name");
    if (shm_name.empty()) {
        std::fprintf(stderr, "capture_host: --shm-name is required\n");
        return 2;
    }

    std::wstring mode = arg_value(argc, argv, L"--mode");
    if (mode.empty()) mode = L"fake";
    if (mode != L"fake" && mode != L"hook") {
        std::fprintf(stderr, "capture_host: --mode must be 'fake' or 'hook'\n");
        return 2;
    }

    int fps = 30;
    {
        const std::wstring v = arg_value(argc, argv, L"--fps");
        if (!v.empty()) fps = _wtoi(v.c_str());
        if (fps < 1) fps = 1;
        if (fps > 240) fps = 240;
    }

    std::wstring target = arg_value(argc, argv, L"--target");
    if (target.empty()) target = L"auto";

    DWORD force_pid = 0;
    {
        const std::wstring v = arg_value(argc, argv, L"--inject-pid");
        if (!v.empty()) force_pid = static_cast<DWORD>(_wtoi(v.c_str()));
    }

    HANDLE parent = nullptr;
    {
        const std::wstring v = arg_value(argc, argv, L"--parent-pid");
        if (!v.empty()) {
            const DWORD pid = static_cast<DWORD>(_wtoi(v.c_str()));
            if (pid != 0) parent = OpenProcess(SYNCHRONIZE, FALSE, pid);
        }
    }

    SetConsoleCtrlHandler(ConsoleHandler, TRUE);
    std::thread watcher(stdin_watch_thread);
    watcher.detach();

    const int rc = (mode == L"hook")
        ? run_hook_mode(shm_name, fps, target, force_pid, parent)
        : run_fake_mode(shm_name, fps, parent);

    logline("exiting (rc=%d)", rc);
    if (parent) CloseHandle(parent);
    return rc;
}
