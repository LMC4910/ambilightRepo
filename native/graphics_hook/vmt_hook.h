// vmt_hook.h — minimal virtual-method-table (vtable) hooking.
//
// COM interface methods (IDXGISwapChain::Present, IDirect3DDevice9::Present, …)
// are always dispatched through the object's vtable, so overwriting the vtable
// slot reliably intercepts every call — no trampoline/disassembler needed. The
// vtable is shared by all instances of the COM class (it lives in the runtime
// DLL), so hooking a slot via a throwaway dummy object also intercepts the game's
// real object. Dependency-free; chains with other overlays (each calls its saved
// original).

#ifndef AMBILIGHT_VMT_HOOK_H
#define AMBILIGHT_VMT_HOOK_H

namespace ambilight {

// Overwrite vtable slot *index* of COM object *instance* with *detour*. Returns
// the original function pointer (call through it), or nullptr on failure.
void* vmt_hook(void* instance, unsigned index, void* detour);

// Restore *original* into slot *index* of *instance*'s vtable.
void vmt_unhook(void* instance, unsigned index, void* original);

}  // namespace ambilight

#endif  // AMBILIGHT_VMT_HOOK_H
