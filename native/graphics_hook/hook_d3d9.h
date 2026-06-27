// hook_d3d9.h — installs the Direct3D 9 Present hook (separate from DXGI; D3D9
// predates DXGI). Only call this when the target actually uses d3d9.dll.

#ifndef AMBILIGHT_HOOK_D3D9_H
#define AMBILIGHT_HOOK_D3D9_H

namespace ambilight {

class ShmWriter;
struct HookControl;

// Install the IDirect3DDevice9::Present hook. Dynamically resolves
// Direct3DCreate9 from the already-loaded d3d9.dll (no link-time d3d9 dependency),
// so injecting into a non-D3D9 game never forces d3d9.dll to load. Returns false
// if d3d9 is unavailable or the hook could not be installed.
bool install_d3d9_hook(ShmWriter* writer, const HookControl* control);

}  // namespace ambilight

#endif  // AMBILIGHT_HOOK_D3D9_H
