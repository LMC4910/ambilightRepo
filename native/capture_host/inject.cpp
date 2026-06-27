// inject.cpp — see inject.h.

#include "inject.h"

namespace ambilight {

bool enable_debug_privilege() {
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(),
                          TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &token)) {
        return false;
    }
    bool ok = false;
    LUID luid{};
    if (LookupPrivilegeValueW(nullptr, SE_DEBUG_NAME, &luid)) {
        TOKEN_PRIVILEGES tp{};
        tp.PrivilegeCount = 1;
        tp.Privileges[0].Luid = luid;
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
        ok = AdjustTokenPrivileges(token, FALSE, &tp, sizeof(tp), nullptr, nullptr) &&
             GetLastError() == ERROR_SUCCESS;
    }
    CloseHandle(token);
    return ok;
}

bool is_wow64_process(DWORD pid) {
    HANDLE proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (proc == nullptr) return false;  // unknown; let injection attempt decide
    BOOL wow64 = FALSE;
    IsWow64Process(proc, &wow64);
    CloseHandle(proc);
    return wow64 == TRUE;
}

const char* inject_status_str(InjectStatus s) {
    switch (s) {
        case InjectStatus::Ok: return "ok";
        case InjectStatus::OpenFailed: return "OpenProcess failed";
        case InjectStatus::AllocFailed: return "VirtualAllocEx failed";
        case InjectStatus::WriteFailed: return "WriteProcessMemory failed";
        case InjectStatus::ThreadFailed: return "CreateRemoteThread failed";
        case InjectStatus::LoadFailed: return "LoadLibraryW returned NULL in target";
    }
    return "unknown";
}

InjectResult inject_dll(DWORD pid, const std::wstring& dll_path) {
    const DWORD access = PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                         PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ;
    HANDLE proc = OpenProcess(access, FALSE, pid);
    if (proc == nullptr) {
        return {InjectStatus::OpenFailed, GetLastError()};
    }

    InjectResult result{InjectStatus::Ok, 0};
    const SIZE_T bytes = (dll_path.size() + 1) * sizeof(wchar_t);
    LPVOID remote = VirtualAllocEx(proc, nullptr, bytes, MEM_COMMIT | MEM_RESERVE,
                                   PAGE_READWRITE);
    if (remote == nullptr) {
        result = {InjectStatus::AllocFailed, GetLastError()};
    } else {
        if (!WriteProcessMemory(proc, remote, dll_path.c_str(), bytes, nullptr)) {
            result = {InjectStatus::WriteFailed, GetLastError()};
        } else {
            // LoadLibraryW lives at the same address in every process this boot
            // (kernel32 is mapped at a fixed base session-wide), so the host's
            // pointer is valid in the target.
            auto loader = reinterpret_cast<LPTHREAD_START_ROUTINE>(
                GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW"));
            HANDLE thread = loader == nullptr ? nullptr
                : CreateRemoteThread(proc, nullptr, 0, loader, remote, 0, nullptr);
            if (thread == nullptr) {
                result = {InjectStatus::ThreadFailed, GetLastError()};
            } else {
                WaitForSingleObject(thread, 10000);
                DWORD exit_code = 0;  // truncated HMODULE; 0 means LoadLibraryW failed
                GetExitCodeThread(thread, &exit_code);
                if (exit_code == 0) {
                    result = {InjectStatus::LoadFailed, GetLastError()};
                }
                CloseHandle(thread);
            }
        }
        VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
    }

    CloseHandle(proc);
    return result;
}

}  // namespace ambilight
