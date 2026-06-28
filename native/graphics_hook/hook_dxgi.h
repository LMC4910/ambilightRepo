// hook_dxgi.h — installs the DXGI Present hook (covers DX10 / DX11; the DX12
// branch is added later). One hook on the shared IDXGISwapChain vtable captures
// every swapchain in the process.

#ifndef AMBILIGHT_HOOK_DXGI_H
#define AMBILIGHT_HOOK_DXGI_H

namespace ambilight {

class ShmWriter;
struct HookControl;

// Install the Present/ResizeBuffers hooks. *writer* receives BGR frames; *control*
// supplies fps + the stop flag. Returns false if the hook could not be installed.
bool install_dxgi_hook(ShmWriter* writer, const HookControl* control);

}  // namespace ambilight

#endif  // AMBILIGHT_HOOK_DXGI_H
