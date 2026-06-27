// hooklog.cpp — see hooklog.h.

#include "hooklog.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <string>

namespace ambilight {

namespace {

std::wstring compute_log_path() {
    wchar_t buf[MAX_PATH];
    const DWORD n = GetEnvironmentVariableW(L"USERPROFILE", buf, MAX_PATH);
    std::wstring dir = (n > 0 && n < MAX_PATH) ? std::wstring(buf, n) : L".";
    dir += L"\\.ambilight";
    CreateDirectoryW(dir.c_str(), nullptr);
    dir += L"\\logs";
    CreateDirectoryW(dir.c_str(), nullptr);
    return dir + L"\\graphics_hook.log";
}

}  // namespace

void hook_log(const char* fmt, ...) {
    char msg[1024];
    va_list ap;
    va_start(ap, fmt);
    _vsnprintf_s(msg, sizeof(msg), _TRUNCATE, fmt, ap);
    va_end(ap);

    OutputDebugStringA("[graphics_hook] ");
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");

    static const std::wstring path = compute_log_path();  // resolved once, thread-safe
    HANDLE f = CreateFileW(path.c_str(), FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    char line[1200];
    const int len = _snprintf_s(line, sizeof(line), _TRUNCATE,
                                "[pid %lu] %s\r\n", GetCurrentProcessId(), msg);
    if (len > 0) {
        DWORD written = 0;
        WriteFile(f, line, static_cast<DWORD>(len), &written, nullptr);
    }
    CloseHandle(f);
}

}  // namespace ambilight
