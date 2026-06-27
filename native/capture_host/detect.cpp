// detect.cpp — see detect.h.

#include "detect.h"

#include <psapi.h>

#include <algorithm>
#include <array>
#include <cwctype>
#include <vector>

namespace ambilight {

namespace {

std::wstring to_lower(std::wstring s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](wchar_t c) { return static_cast<wchar_t>(std::towlower(c)); });
    return s;
}

std::wstring basename_lower(const std::wstring& path) {
    const size_t slash = path.find_last_of(L"\\/");
    return to_lower(slash == std::wstring::npos ? path : path.substr(slash + 1));
}

// Shells, the compositor, browsers, and our own/overlay processes are never the
// game we want — exclude them up front (also keeps us from injecting into the
// desktop shell). The Direct3D-module gate below catches most non-games anyway.
bool on_denylist(const std::wstring& exe) {
    static const std::array<const wchar_t*, 16> kDeny = {
        L"explorer.exe", L"dwm.exe", L"applicationframehost.exe",
        L"searchhost.exe", L"startmenuexperiencehost.exe",
        L"shellexperiencehost.exe", L"textinputhost.exe", L"sihost.exe",
        L"chrome.exe", L"firefox.exe", L"msedge.exe", L"brave.exe",
        L"opera.exe", L"obs64.exe", L"obs32.exe", L"capture_host.exe",
    };
    for (const wchar_t* d : kDeny) {
        if (exe == d) return true;
    }
    return false;
}

std::wstring exe_path_of(DWORD pid) {
    HANDLE proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (proc == nullptr) return L"";
    wchar_t buf[MAX_PATH];
    DWORD size = MAX_PATH;
    std::wstring path;
    if (QueryFullProcessImageNameW(proc, 0, buf, &size)) {
        path.assign(buf, size);
    }
    CloseHandle(proc);
    return path;
}

// True if the window covers (within a small tolerance) the monitor it is on.
bool is_fullscreen(HWND hwnd) {
    RECT wr{};
    if (!GetWindowRect(hwnd, &wr)) return false;
    HMONITOR mon = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
    MONITORINFO mi{};
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoW(mon, &mi)) return false;
    const LONG tol = 2;  // borderless windows occasionally sit 1px off
    const RECT& m = mi.rcMonitor;
    return wr.left <= m.left + tol && wr.top <= m.top + tol &&
           wr.right >= m.right - tol && wr.bottom >= m.bottom - tol;
}

// True if the process has any Direct3D runtime module loaded — our "is this a
// game" heuristic (and a precondition for the hook to have anything to hook).
bool has_direct3d(DWORD pid, std::wstring& which) {
    HANDLE proc = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
    if (proc == nullptr) return false;

    std::vector<HMODULE> mods(512);
    DWORD needed = 0;
    bool found = false;
    if (EnumProcessModulesEx(proc, mods.data(),
                             static_cast<DWORD>(mods.size() * sizeof(HMODULE)),
                             &needed, LIST_MODULES_ALL)) {
        const size_t count = std::min<size_t>(mods.size(), needed / sizeof(HMODULE));
        static const std::array<const wchar_t*, 6> kD3D = {
            L"dxgi.dll", L"d3d9.dll", L"d3d10.dll", L"d3d11.dll", L"d3d12.dll",
            L"d3d10core.dll",
        };
        for (size_t i = 0; i < count && !found; ++i) {
            wchar_t name[MAX_PATH];
            if (GetModuleBaseNameW(proc, mods[i], name, MAX_PATH) == 0) continue;
            const std::wstring base = to_lower(name);
            for (const wchar_t* d : kD3D) {
                if (base == d) { which = base; found = true; break; }
            }
        }
    }
    CloseHandle(proc);
    return found;
}

}  // namespace

bool process_alive(DWORD pid) {
    HANDLE proc = OpenProcess(SYNCHRONIZE, FALSE, pid);
    if (proc == nullptr) return false;
    const DWORD wait = WaitForSingleObject(proc, 0);
    CloseHandle(proc);
    return wait == WAIT_TIMEOUT;  // still running
}

bool detect_foreground_game(const std::wstring& target_filter,
                            GameTarget& out, std::string& reason) {
    HWND hwnd = GetForegroundWindow();
    if (hwnd == nullptr) { reason = "no foreground window"; return false; }

    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (pid == 0) { reason = "no pid"; return false; }
    if (pid == GetCurrentProcessId()) { reason = "self"; return false; }

    const std::wstring exe = basename_lower(exe_path_of(pid));
    if (exe.empty()) { reason = "exe unreadable"; return false; }

    char exe_utf8[MAX_PATH] = {0};
    WideCharToMultiByte(CP_UTF8, 0, exe.c_str(), -1, exe_utf8, sizeof(exe_utf8), nullptr, nullptr);

    if (on_denylist(exe)) { reason = std::string(exe_utf8) + ": denylisted"; return false; }

    if (target_filter != L"auto" && !target_filter.empty()) {
        // Case-insensitive substring match (mirrors auto_profile.match_profile).
        if (to_lower(exe).find(to_lower(target_filter)) == std::wstring::npos) {
            reason = std::string(exe_utf8) + ": does not match --target filter";
            return false;
        }
    }

    if (!is_fullscreen(hwnd)) { reason = std::string(exe_utf8) + ": not fullscreen"; return false; }

    std::wstring which;
    if (!has_direct3d(pid, which)) {
        reason = std::string(exe_utf8) + ": no Direct3D module (not a game)";
        return false;
    }

    char which_utf8[64] = {0};
    WideCharToMultiByte(CP_UTF8, 0, which.c_str(), -1, which_utf8, sizeof(which_utf8), nullptr, nullptr);
    reason = std::string(exe_utf8) + ": fullscreen game (" + which_utf8 + ")";
    out = GameTarget{pid, exe, hwnd};
    return true;
}

}  // namespace ambilight
