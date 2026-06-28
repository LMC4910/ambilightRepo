// hook_vulkan.h — installs the Vulkan present hook (separate from DXGI/D3D9).
// Only call this when the target actually uses vulkan-1.dll.

#ifndef AMBILIGHT_HOOK_VULKAN_H
#define AMBILIGHT_HOOK_VULKAN_H

namespace ambilight {

class ShmWriter;
struct HookControl;

// Install the vkQueuePresentKHR hook (plus vkCreateSwapchainKHR /
// vkDestroySwapchainKHR / vkGetDeviceQueue helpers). Resolves every Vulkan entry
// point at runtime from the already-loaded vulkan-1.dll (no link-time loader
// dependency), so injecting into a non-Vulkan game never forces vulkan-1.dll to
// load. Returns false if Vulkan is unavailable or the hook could not be installed.
bool install_vulkan_hook(ShmWriter* writer, const HookControl* control);

}  // namespace ambilight

#endif  // AMBILIGHT_HOOK_VULKAN_H
