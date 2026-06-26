// capture_host.exe — the native side of the hook capture transport.
//
// Phase 1 (this file): a FAKE frame source. It attaches to the Python-owned
// shared mapping and writes an animated BGR rainbow at the requested FPS. This
// proves the full Python <-> shared-memory <-> host path end-to-end before any
// DLL injection or DirectX hooking exists.
//
// Phase 2 (future): add `--mode hook --target <exe>` that injects graphics_hook
// into a DX11 game and writes real backbuffer frames through the SAME ShmWriter.
//
// Lifecycle: exits cleanly when stdin reaches EOF (Python closed the pipe / died)
// or when --parent-pid is supplied and that process exits. This guarantees the
// host never lingers as an orphan after Python goes away.
//
// Usage:
//   capture_host.exe --shm-name <NAME> [--fps 30] [--mode fake] [--parent-pid N]

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "shm_protocol.h"
#include "shm_writer.h"

namespace {

std::atomic<bool> g_running{true};

BOOL WINAPI ConsoleHandler(DWORD) {
    g_running.store(false);
    return TRUE;
}

// Microsecond steady clock for frame timestamps.
uint64_t now_us() {
    using namespace std::chrono;
    return static_cast<uint64_t>(
        duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count());
}

// Watches stdin; when the pipe closes (Python exits), stop the loop. Runs on its
// own thread because reads block. ReadFile on a broken/closed pipe returns FALSE
// or 0 bytes, which we treat as EOF.
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

}  // namespace

int wmain(int argc, wchar_t** argv) {
    const std::wstring shm_name = arg_value(argc, argv, L"--shm-name");
    if (shm_name.empty()) {
        std::fprintf(stderr, "capture_host: --shm-name is required\n");
        return 2;
    }

    std::wstring mode_val = arg_value(argc, argv, L"--mode");
    if (mode_val.empty()) mode_val = L"fake";
    if (mode_val != L"fake") {
        std::fprintf(stderr, "capture_host: only --mode fake is supported in Phase 1\n");
        return 2;
    }

    int fps = 30;
    {
        const std::wstring v = arg_value(argc, argv, L"--fps");
        if (!v.empty()) fps = _wtoi(v.c_str());
        if (fps < 1) fps = 1;
        if (fps > 240) fps = 240;
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

    ambilight::ShmWriter writer;
    if (!writer.open(shm_name)) {
        std::fprintf(stderr, "capture_host: %s\n", writer.last_error().c_str());
        if (parent) CloseHandle(parent);
        return 1;
    }

    const uint32_t w = writer.max_width();
    const uint32_t h = writer.max_height();
    std::fprintf(stderr, "capture_host: attached %ux%u @ %d fps (fake)\n", w, h, fps);
    std::fflush(stderr);

    std::thread watcher(stdin_watch_thread);
    watcher.detach();

    // Precompute one row's worth of BGR; every row is identical (vertical
    // rainbow bands that scroll horizontally over time), so per-frame cost is
    // O(width) HSV conversions + memcpy of the rows.
    std::vector<uint8_t> row(static_cast<size_t>(w) * 3u);
    std::vector<uint8_t> frame(static_cast<size_t>(w) * static_cast<size_t>(h) * 3u);

    const auto frame_interval = std::chrono::microseconds(1000000 / fps);
    uint64_t tick = 0;
    auto next = std::chrono::steady_clock::now();

    while (g_running.load() && parent_alive(parent)) {
        const double phase = static_cast<double>(tick) * 0.01;  // scroll speed
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

    std::fprintf(stderr, "capture_host: exiting\n");
    if (parent) CloseHandle(parent);
    return 0;
}
