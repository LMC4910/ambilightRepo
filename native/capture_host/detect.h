// detect.h — foreground "game" detection for capture_host.
//
// A target qualifies when it is: the foreground window, covering a full monitor
// (borderless or exclusive fullscreen), backed by a process that has a Direct3D
// module loaded (the "is it a game" signal), not on a shell/browser denylist,
// and matching the optional exe filter.

#ifndef AMBILIGHT_DETECT_H
#define AMBILIGHT_DETECT_H

#include <string>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace ambilight {

struct GameTarget {
    DWORD pid = 0;
    std::wstring exe;   // lowercase basename, e.g. L"witcher3.exe"
    HWND hwnd = nullptr;
};

// Inspect the foreground window. Returns true and fills *out* if it is a
// qualifying fullscreen Direct3D game. *reason* always receives a short,
// human-readable explanation of the decision (for logging).
//
// *target_filter* is L"auto" (any game) or a substring matched case-insensitively
// against the exe basename (same rule as the Python auto_profile matcher).
bool detect_foreground_game(const std::wstring& target_filter,
                            GameTarget& out, std::string& reason);

// True if *pid* still refers to a live process.
bool process_alive(DWORD pid);

}  // namespace ambilight

#endif  // AMBILIGHT_DETECT_H
