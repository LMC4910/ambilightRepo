// hook_control.h — the small fixed-name "control" shared mapping that lets
// capture_host.exe hand the injected graphics_hook.dll everything it needs to
// start writing frames.
//
// capture_host CREATES this mapping (writer) before injecting the DLL; the DLL
// OPENS it by the well-known name, reads the frame-buffer mapping name + fps,
// and watches `stop`. Single capture session → a fixed name is sufficient.
//
// This is a separate, tiny mapping from the frame ring buffer (shm_protocol.h):
// the frame buffer is Python-owned with an auto-generated name, so the DLL can
// only learn that name through this control channel.

#ifndef AMBILIGHT_HOOK_CONTROL_H
#define AMBILIGHT_HOOK_CONTROL_H

#include <cstdint>

// Well-known name of the control mapping (session-local namespace).
#define AMBILIGHT_HOOK_CONTROL_NAME L"Local\\AmbilightHookControl"

namespace ambilight {

constexpr uint32_t HOOK_CONTROL_MAGIC = 0x4B4F4F48u;  // 'HOOK'
constexpr uint32_t HOOK_CONTROL_VERSION = 1u;
constexpr uint32_t HOOK_SHM_NAME_MAX = 256u;

#pragma pack(push, 1)
struct HookControl {
    uint32_t magic;        // HOOK_CONTROL_MAGIC
    uint32_t version;      // HOOK_CONTROL_VERSION
    uint32_t fps;          // target capture frame rate
    uint32_t stop;         // non-zero => the DLL must stop writing frames
    char     shm_name[HOOK_SHM_NAME_MAX];  // frame-buffer mapping name (ASCII, NUL-terminated)
};
#pragma pack(pop)

static_assert(sizeof(HookControl) == 16 + HOOK_SHM_NAME_MAX, "HookControl layout drift");

}  // namespace ambilight

#endif  // AMBILIGHT_HOOK_CONTROL_H
