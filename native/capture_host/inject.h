// inject.h — DLL injection + privilege helpers for capture_host.
//
// Loads graphics_hook.dll into a target game with the classic
// VirtualAllocEx + WriteProcessMemory + CreateRemoteThread(LoadLibraryW) dance.

#ifndef AMBILIGHT_INJECT_H
#define AMBILIGHT_INJECT_H

#include <string>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace ambilight {

// Best-effort: enable SeDebugPrivilege so we can open/inject games started by
// other sessions or launchers. Returns false if it could not be enabled (we
// still try injection — many same-integrity games need no special privilege).
bool enable_debug_privilege();

// True if the target process is 32-bit (WOW64) on this 64-bit host. We only
// inject our x64 DLL into x64 processes, so a true result means "skip".
bool is_wow64_process(DWORD pid);

enum class InjectStatus { Ok, OpenFailed, AllocFailed, WriteFailed, ThreadFailed, LoadFailed };

struct InjectResult {
    InjectStatus status;
    DWORD win32_error;  // GetLastError at the point of failure (0 on success)
};

// Inject *dll_path* into *pid*. Synchronous: waits for LoadLibraryW to return.
InjectResult inject_dll(DWORD pid, const std::wstring& dll_path);

const char* inject_status_str(InjectStatus s);

}  // namespace ambilight

#endif  // AMBILIGHT_INJECT_H
