// vmt_hook.cpp — see vmt_hook.h.

#include "vmt_hook.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace ambilight {

void* vmt_hook(void* instance, unsigned index, void* detour) {
    if (instance == nullptr || detour == nullptr) return nullptr;
    void** vtable = *reinterpret_cast<void***>(instance);
    void** slot = &vtable[index];

    DWORD old_protect = 0;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_EXECUTE_READWRITE, &old_protect)) {
        return nullptr;
    }
    void* original = *slot;
    *slot = detour;
    VirtualProtect(slot, sizeof(void*), old_protect, &old_protect);
    return original;
}

void vmt_unhook(void* instance, unsigned index, void* original) {
    if (instance == nullptr || original == nullptr) return;
    void** vtable = *reinterpret_cast<void***>(instance);
    void** slot = &vtable[index];

    DWORD old_protect = 0;
    if (!VirtualProtect(slot, sizeof(void*), PAGE_EXECUTE_READWRITE, &old_protect)) {
        return;
    }
    *slot = original;
    VirtualProtect(slot, sizeof(void*), old_protect, &old_protect);
}

}  // namespace ambilight
