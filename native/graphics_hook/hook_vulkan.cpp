// hook_vulkan.cpp — see hook_vulkan.h.
//
// Intercepts Vulkan presentation to capture the swapchain image for the colour
// pipeline, mirroring the DX paths (throttle → foreground-gate → copy → BGR →
// ShmWriter, always calling the original). The Vulkan model has no "get the
// backbuffer" convenience, so we:
//
//   * hook vkCreateSwapchainKHR and OR VK_IMAGE_USAGE_TRANSFER_SRC_BIT into
//     imageUsage so the presented images are copyable (the standard technique);
//     we then record the device/format/extent and the swapchain's images;
//   * on vkQueuePresentKHR, record a one-shot command buffer that transitions the
//     presented image PRESENT_SRC_KHR → TRANSFER_SRC_OPTIMAL, copies it to a
//     host-visible buffer, and transitions it back, submitted on the SAME queue
//     the app presents on (so it is ordered after the app's render work on that
//     queue) and fenced so the CPU read sees a complete copy;
//   * convert the mapped pixels to packed BGR and publish.
//
// Injection happens after the game has already created its VkDevice, so we do NOT
// depend on having observed device creation: memory-type properties are taken
// from our own throwaway instance (correct on single-GPU systems, the norm), and
// the queue family is learned from vkGetDeviceQueue when available (falling back
// to family 0). We DO need to observe the swapchain's creation — fullscreen games
// recreate their swapchain on fullscreen entry/resize, which is caught after we
// inject; a swapchain that predates injection is skipped until it is recreated.

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan_core.h>

#include <chrono>
#include <cstdint>
#include <map>
#include <mutex>
#include <vector>

#include "hook_vulkan.h"
#include "shm_writer.h"
#include "hook_control.h"
#include "hooklog.h"

#include <MinHook.h>

namespace ambilight {

namespace {

// ---- resolved (non-hooked) Vulkan entry points -----------------------------
PFN_vkGetInstanceProcAddr            p_vkGetInstanceProcAddr = nullptr;
PFN_vkCreateInstance                 p_vkCreateInstance = nullptr;
PFN_vkEnumeratePhysicalDevices       p_vkEnumeratePhysicalDevices = nullptr;
PFN_vkGetPhysicalDeviceProperties    p_vkGetPhysicalDeviceProperties = nullptr;
PFN_vkGetPhysicalDeviceMemoryProperties p_vkGetPhysicalDeviceMemoryProperties = nullptr;
PFN_vkGetSwapchainImagesKHR          p_vkGetSwapchainImagesKHR = nullptr;
PFN_vkCreateCommandPool              p_vkCreateCommandPool = nullptr;
PFN_vkDestroyCommandPool             p_vkDestroyCommandPool = nullptr;
PFN_vkAllocateCommandBuffers         p_vkAllocateCommandBuffers = nullptr;
PFN_vkCreateBuffer                   p_vkCreateBuffer = nullptr;
PFN_vkDestroyBuffer                  p_vkDestroyBuffer = nullptr;
PFN_vkGetBufferMemoryRequirements    p_vkGetBufferMemoryRequirements = nullptr;
PFN_vkAllocateMemory                 p_vkAllocateMemory = nullptr;
PFN_vkFreeMemory                     p_vkFreeMemory = nullptr;
PFN_vkBindBufferMemory               p_vkBindBufferMemory = nullptr;
PFN_vkMapMemory                      p_vkMapMemory = nullptr;
PFN_vkUnmapMemory                    p_vkUnmapMemory = nullptr;
PFN_vkCreateFence                    p_vkCreateFence = nullptr;
PFN_vkDestroyFence                   p_vkDestroyFence = nullptr;
PFN_vkResetFences                    p_vkResetFences = nullptr;
PFN_vkWaitForFences                  p_vkWaitForFences = nullptr;
PFN_vkBeginCommandBuffer             p_vkBeginCommandBuffer = nullptr;
PFN_vkEndCommandBuffer               p_vkEndCommandBuffer = nullptr;
PFN_vkResetCommandBuffer             p_vkResetCommandBuffer = nullptr;
PFN_vkCmdPipelineBarrier             p_vkCmdPipelineBarrier = nullptr;
PFN_vkCmdCopyImageToBuffer           p_vkCmdCopyImageToBuffer = nullptr;
PFN_vkQueueSubmit                    p_vkQueueSubmit = nullptr;

// ---- hooked entry points (originals via MinHook trampoline) -----------------
PFN_vkCreateSwapchainKHR  g_orig_vkCreateSwapchainKHR = nullptr;
PFN_vkDestroySwapchainKHR g_orig_vkDestroySwapchainKHR = nullptr;
PFN_vkGetDeviceQueue      g_orig_vkGetDeviceQueue = nullptr;
PFN_vkGetDeviceQueue2     g_orig_vkGetDeviceQueue2 = nullptr;
PFN_vkQueuePresentKHR     g_orig_vkQueuePresentKHR = nullptr;

// ---- capture state ---------------------------------------------------------
struct CaptureRes {
    VkDevice device = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer cmd = VK_NULL_HANDLE;
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    uint32_t family = UINT32_MAX;
    uint32_t width = 0;
    uint32_t height = 0;
};

struct SwapchainInfo {
    VkDevice device = VK_NULL_HANDLE;
    VkFormat format = VK_FORMAT_UNDEFINED;
    uint32_t width = 0;
    uint32_t height = 0;
    bool capturable = false;          // images carry TRANSFER_SRC usage
    std::vector<VkImage> images;
    CaptureRes res;
};

struct QueueInfo { VkDevice device; uint32_t family; };

std::mutex g_mutex;
std::map<VkQueue, QueueInfo> g_queues;
std::map<VkSwapchainKHR, SwapchainInfo> g_swapchains;

ShmWriter* g_writer = nullptr;
const HookControl* g_control = nullptr;
long long g_frame_interval_us = 33333;
std::chrono::steady_clock::time_point g_last_capture{};
std::vector<uint8_t> g_scratch;
bool g_logged_first = false;
VkFormat g_warned_fmt = VK_FORMAT_UNDEFINED;
bool g_warned_predates = false;

// Memory properties of a representative GPU (single-GPU systems: the game's GPU).
VkPhysicalDeviceMemoryProperties g_mem_props{};
bool g_mem_ready = false;

long long now_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

// Convert a tightly-packed 4-byte-per-pixel Vulkan image to packed BGR. Supports
// the common SDR swapchain formats; returns false (SDR only) otherwise.
bool vk_to_bgr(const uint8_t* src, uint32_t width, uint32_t height, VkFormat fmt,
               std::vector<uint8_t>& out) {
    bool bgra;  // true: bytes are B,G,R,A ; false: bytes are R,G,B,A
    switch (fmt) {
        case VK_FORMAT_B8G8R8A8_UNORM:
        case VK_FORMAT_B8G8R8A8_SRGB:
            bgra = true; break;
        case VK_FORMAT_R8G8B8A8_UNORM:
        case VK_FORMAT_R8G8B8A8_SRGB:
        case VK_FORMAT_A8B8G8R8_UNORM_PACK32:  // little-endian bytes == R,G,B,A
        case VK_FORMAT_A8B8G8R8_SRGB_PACK32:
            bgra = false; break;
        default:
            return false;  // 10-bit / HDR / packed — unsupported (SDR only)
    }
    out.resize(static_cast<size_t>(width) * height * 3);
    const uint32_t pitch = width * 4;
    uint8_t* dst = out.data();
    for (uint32_t y = 0; y < height; ++y) {
        const uint8_t* row = src + static_cast<size_t>(y) * pitch;
        for (uint32_t x = 0; x < width; ++x) {
            const uint8_t* px = row + static_cast<size_t>(x) * 4;
            if (bgra) {
                *dst++ = px[0]; *dst++ = px[1]; *dst++ = px[2];  // B,G,R
            } else {
                *dst++ = px[2]; *dst++ = px[1]; *dst++ = px[0];  // R,G,B -> B,G,R
            }
        }
    }
    return true;
}

// Populate g_mem_props from a throwaway instance once. We do not observe the
// game's vkCreateDevice (it runs before injection), so we read the GPU's memory
// layout ourselves — identical to the game's device on single-GPU systems.
bool ensure_mem_props() {
    if (g_mem_ready) return true;
    if (!p_vkCreateInstance || !p_vkEnumeratePhysicalDevices ||
        !p_vkGetPhysicalDeviceMemoryProperties) {
        return false;
    }
    VkApplicationInfo app{};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.apiVersion = VK_API_VERSION_1_0;
    VkInstanceCreateInfo ici{};
    ici.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    ici.pApplicationInfo = &app;
    VkInstance inst = VK_NULL_HANDLE;
    if (p_vkCreateInstance(&ici, nullptr, &inst) != VK_SUCCESS || inst == VK_NULL_HANDLE) {
        hook_log("Vulkan: probe instance creation failed (can't read memory types)");
        return false;
    }
    uint32_t count = 0;
    p_vkEnumeratePhysicalDevices(inst, &count, nullptr);
    if (count == 0) return false;
    std::vector<VkPhysicalDevice> gpus(count);
    p_vkEnumeratePhysicalDevices(inst, &count, gpus.data());
    VkPhysicalDevice chosen = gpus[0];
    if (p_vkGetPhysicalDeviceProperties) {
        for (auto gpu : gpus) {
            VkPhysicalDeviceProperties props{};
            p_vkGetPhysicalDeviceProperties(gpu, &props);
            if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) { chosen = gpu; break; }
        }
    }
    p_vkGetPhysicalDeviceMemoryProperties(chosen, &g_mem_props);
    g_mem_ready = true;
    // Deliberately leak the probe instance — destroying it after this is harmless
    // but keeping it avoids any teardown ordering concerns; one instance, once.
    return true;
}

uint32_t find_mem_type(uint32_t type_bits, VkMemoryPropertyFlags want) {
    for (uint32_t i = 0; i < g_mem_props.memoryTypeCount; ++i) {
        if ((type_bits & (1u << i)) &&
            (g_mem_props.memoryTypes[i].propertyFlags & want) == want) {
            return i;
        }
    }
    return UINT32_MAX;
}

void destroy_res(CaptureRes& r) {
    if (r.device == VK_NULL_HANDLE) return;
    if (r.fence)  p_vkDestroyFence(r.device, r.fence, nullptr);
    if (r.buffer) p_vkDestroyBuffer(r.device, r.buffer, nullptr);
    if (r.memory) p_vkFreeMemory(r.device, r.memory, nullptr);
    if (r.pool)   p_vkDestroyCommandPool(r.device, r.pool, nullptr);  // frees cmd too
    r = CaptureRes{};
}

// Lazily (re)create per-swapchain capture resources for the given geometry/family.
bool ensure_res(SwapchainInfo& si, uint32_t family) {
    CaptureRes& r = si.res;
    if (r.cmd != VK_NULL_HANDLE && r.width == si.width && r.height == si.height &&
        r.family == family) {
        return true;
    }
    destroy_res(r);
    if (!ensure_mem_props()) return false;

    r.device = si.device;
    r.family = family;
    r.width = si.width;
    r.height = si.height;

    VkCommandPoolCreateInfo pci{};
    pci.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pci.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    pci.queueFamilyIndex = family;
    if (p_vkCreateCommandPool(r.device, &pci, nullptr, &r.pool) != VK_SUCCESS) { destroy_res(r); return false; }

    VkCommandBufferAllocateInfo cbi{};
    cbi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    cbi.commandPool = r.pool;
    cbi.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cbi.commandBufferCount = 1;
    if (p_vkAllocateCommandBuffers(r.device, &cbi, &r.cmd) != VK_SUCCESS) { destroy_res(r); return false; }

    VkBufferCreateInfo bci{};
    bci.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    bci.size = static_cast<VkDeviceSize>(si.width) * si.height * 4;
    bci.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    bci.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    if (p_vkCreateBuffer(r.device, &bci, nullptr, &r.buffer) != VK_SUCCESS) { destroy_res(r); return false; }

    VkMemoryRequirements mr{};
    p_vkGetBufferMemoryRequirements(r.device, r.buffer, &mr);
    const uint32_t mt = find_mem_type(
        mr.memoryTypeBits,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    if (mt == UINT32_MAX) { hook_log("Vulkan: no host-visible memory type"); destroy_res(r); return false; }

    VkMemoryAllocateInfo mai{};
    mai.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    mai.allocationSize = mr.size;
    mai.memoryTypeIndex = mt;
    if (p_vkAllocateMemory(r.device, &mai, nullptr, &r.memory) != VK_SUCCESS) { destroy_res(r); return false; }
    if (p_vkBindBufferMemory(r.device, r.buffer, r.memory, 0) != VK_SUCCESS) { destroy_res(r); return false; }

    VkFenceCreateInfo fci{};
    fci.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    if (p_vkCreateFence(r.device, &fci, nullptr, &r.fence) != VK_SUCCESS) { destroy_res(r); return false; }
    return true;
}

// Record + submit the image→buffer copy on *queue*, fenced. Returns true when the
// copy has completed and the readback buffer holds the frame.
bool copy_image(SwapchainInfo& si, VkQueue queue, VkImage image) {
    CaptureRes& r = si.res;
    p_vkResetCommandBuffer(r.cmd, 0);

    VkCommandBufferBeginInfo bi{};
    bi.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    if (p_vkBeginCommandBuffer(r.cmd, &bi) != VK_SUCCESS) return false;

    VkImageMemoryBarrier to_src{};
    to_src.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    to_src.srcAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    to_src.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    to_src.oldLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    to_src.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    to_src.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_src.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    to_src.image = image;
    to_src.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    p_vkCmdPipelineBarrier(r.cmd, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
                           VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &to_src);

    VkBufferImageCopy region{};
    region.bufferOffset = 0;
    region.bufferRowLength = 0;    // tightly packed (== width)
    region.bufferImageHeight = 0;
    region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    region.imageOffset = {0, 0, 0};
    region.imageExtent = {si.width, si.height, 1};
    p_vkCmdCopyImageToBuffer(r.cmd, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                             r.buffer, 1, &region);

    VkImageMemoryBarrier to_present = to_src;
    to_present.srcAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    to_present.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    to_present.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    to_present.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    p_vkCmdPipelineBarrier(r.cmd, VK_PIPELINE_STAGE_TRANSFER_BIT,
                           VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 1, &to_present);

    if (p_vkEndCommandBuffer(r.cmd) != VK_SUCCESS) return false;

    VkSubmitInfo si_submit{};
    si_submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    si_submit.commandBufferCount = 1;
    si_submit.pCommandBuffers = &r.cmd;

    p_vkResetFences(r.device, 1, &r.fence);
    if (p_vkQueueSubmit(queue, 1, &si_submit, r.fence) != VK_SUCCESS) return false;
    return p_vkWaitForFences(r.device, 1, &r.fence, VK_TRUE, 1000000000ull) == VK_SUCCESS;
}

void capture_present(VkQueue queue, const VkPresentInfoKHR* pi) {
    const auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration_cast<std::chrono::microseconds>(now - g_last_capture).count()
            < g_frame_interval_us) {
        return;
    }
    if (g_control && g_control->stop) return;
    if (g_writer == nullptr) return;

    static int fg_gate = -1;
    if (fg_gate == -1) {
        wchar_t v[8] = {0};
        const DWORD n = GetEnvironmentVariableW(L"AMBILIGHT_HOOK_CAPTURE_ALL", v, 8);
        fg_gate = (n > 0 && v[0] == L'1') ? 0 : 1;
    }
    if (fg_gate) {
        DWORD pid = 0;
        GetWindowThreadProcessId(GetForegroundWindow(), &pid);
        if (pid != GetCurrentProcessId()) return;
    }

    if (pi == nullptr || pi->swapchainCount == 0 || pi->pSwapchains == nullptr ||
        pi->pImageIndices == nullptr) {
        return;
    }

    // Hold the lock only for the map lookups — never across the Vulkan/driver
    // calls below. A hardware fault inside a driver call propagates to the SEH
    // handler, which does not run C++ destructors, so a lock held here would never
    // be released and would deadlock the game. std::map nodes are pointer-stable,
    // so the pointer stays valid after we unlock (the app never destroys a
    // swapchain concurrently with presenting that same swapchain).
    SwapchainInfo* sip = nullptr;
    uint32_t family = 0;  // fallback: family 0 (graphics) when not observed
    {
        std::lock_guard<std::mutex> lk(g_mutex);
        const VkSwapchainKHR sc = pi->pSwapchains[0];
        auto sit = g_swapchains.find(sc);
        if (sit == g_swapchains.end()) {
            if (!g_warned_predates) {
                hook_log("Vulkan: presented swapchain predates injection; waiting for it to be "
                         "recreated (toggle fullscreen if it never is)");
                g_warned_predates = true;
            }
            return;
        }
        if (!sit->second.capturable) return;
        sip = &sit->second;
        auto qit = g_queues.find(queue);
        if (qit != g_queues.end()) family = qit->second.family;
    }

    SwapchainInfo& si = *sip;
    const uint32_t idx = pi->pImageIndices[0];
    if (idx >= si.images.size()) return;
    const VkImage image = si.images[idx];

    if (!ensure_res(si, family)) return;
    if (!copy_image(si, queue, image)) return;

    void* mapped = nullptr;
    if (p_vkMapMemory(si.res.device, si.res.memory, 0, VK_WHOLE_SIZE, 0, &mapped) != VK_SUCCESS) {
        return;
    }
    if (vk_to_bgr(static_cast<const uint8_t*>(mapped), si.width, si.height, si.format, g_scratch)) {
        if (g_writer->write_frame(g_scratch.data(), si.width, si.height,
                                  static_cast<uint64_t>(now_us()))) {
            g_last_capture = now;
            if (!g_logged_first) {
                hook_log("Vulkan capture live: %ux%u fmt=%d", si.width, si.height,
                         static_cast<int>(si.format));
                g_logged_first = true;
            }
        }
    } else if (g_warned_fmt != si.format) {
        hook_log("unsupported Vulkan format %d (SDR only); skipping", static_cast<int>(si.format));
        g_warned_fmt = si.format;
    }
    p_vkUnmapMemory(si.res.device, si.res.memory);
}

// SEH wrapper: no C++ objects with destructors live here (a driver fault inside
// capture must never crash the game), so unwinding is not required.
void capture_present_seh(VkQueue queue, const VkPresentInfoKHR* pi) {
    __try {
        capture_present(queue, pi);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
    }
}

// ---- detours ---------------------------------------------------------------

VkResult VKAPI_CALL d_vkCreateSwapchainKHR(VkDevice device,
                                           const VkSwapchainCreateInfoKHR* pCreateInfo,
                                           const VkAllocationCallbacks* pAllocator,
                                           VkSwapchainKHR* pSwapchain) {
    bool capturable = true;
    VkSwapchainCreateInfoKHR mod = *pCreateInfo;
    mod.imageUsage |= VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    VkResult r = g_orig_vkCreateSwapchainKHR(device, &mod, pAllocator, pSwapchain);
    if (r != VK_SUCCESS) {
        // A driver that rejects the extra usage (rare) — fall back to the app's
        // original request so the game is never broken; that swapchain just can't
        // be captured.
        capturable = false;
        r = g_orig_vkCreateSwapchainKHR(device, pCreateInfo, pAllocator, pSwapchain);
    }
    if (r == VK_SUCCESS && pSwapchain != nullptr && *pSwapchain != VK_NULL_HANDLE) {
        SwapchainInfo si;
        si.device = device;
        si.format = pCreateInfo->imageFormat;
        si.width = pCreateInfo->imageExtent.width;
        si.height = pCreateInfo->imageExtent.height;
        si.capturable = capturable;
        if (capturable && p_vkGetSwapchainImagesKHR) {
            uint32_t n = 0;
            p_vkGetSwapchainImagesKHR(device, *pSwapchain, &n, nullptr);
            if (n > 0) {
                si.images.resize(n);
                p_vkGetSwapchainImagesKHR(device, *pSwapchain, &n, si.images.data());
            }
        }
        std::lock_guard<std::mutex> lk(g_mutex);
        g_swapchains[*pSwapchain] = std::move(si);
        hook_log("Vulkan swapchain created: %ux%u fmt=%d images=%u%s",
                 pCreateInfo->imageExtent.width, pCreateInfo->imageExtent.height,
                 static_cast<int>(pCreateInfo->imageFormat),
                 static_cast<unsigned>(g_swapchains[*pSwapchain].images.size()),
                 capturable ? "" : " (not capturable)");
    }
    return r;
}

void VKAPI_CALL d_vkDestroySwapchainKHR(VkDevice device, VkSwapchainKHR swapchain,
                                        const VkAllocationCallbacks* pAllocator) {
    {
        std::lock_guard<std::mutex> lk(g_mutex);
        auto it = g_swapchains.find(swapchain);
        if (it != g_swapchains.end()) {
            destroy_res(it->second.res);
            g_swapchains.erase(it);
        }
    }
    g_orig_vkDestroySwapchainKHR(device, swapchain, pAllocator);
}

void VKAPI_CALL d_vkGetDeviceQueue(VkDevice device, uint32_t queueFamilyIndex,
                                   uint32_t queueIndex, VkQueue* pQueue) {
    g_orig_vkGetDeviceQueue(device, queueFamilyIndex, queueIndex, pQueue);
    if (pQueue != nullptr && *pQueue != VK_NULL_HANDLE) {
        std::lock_guard<std::mutex> lk(g_mutex);
        g_queues[*pQueue] = {device, queueFamilyIndex};
    }
}

void VKAPI_CALL d_vkGetDeviceQueue2(VkDevice device, const VkDeviceQueueInfo2* pQueueInfo,
                                    VkQueue* pQueue) {
    g_orig_vkGetDeviceQueue2(device, pQueueInfo, pQueue);
    if (pQueueInfo != nullptr && pQueue != nullptr && *pQueue != VK_NULL_HANDLE) {
        std::lock_guard<std::mutex> lk(g_mutex);
        g_queues[*pQueue] = {device, pQueueInfo->queueFamilyIndex};
    }
}

VkResult VKAPI_CALL d_vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR* pPresentInfo) {
    capture_present_seh(queue, pPresentInfo);
    return g_orig_vkQueuePresentKHR(queue, pPresentInfo);
}

// ---- install ---------------------------------------------------------------

template <typename T>
bool hook_one(HMODULE vk, const char* name, LPVOID detour, T* orig) {
    void* target = reinterpret_cast<void*>(GetProcAddress(vk, name));
    if (target == nullptr) return false;
    if (MH_CreateHook(target, detour, reinterpret_cast<LPVOID*>(orig)) != MH_OK ||
        MH_EnableHook(target) != MH_OK) {
        hook_log("Vulkan: MinHook failed to hook %s", name);
        return false;
    }
    return true;
}

}  // namespace

bool install_vulkan_hook(ShmWriter* writer, const HookControl* control) {
    HMODULE vk = GetModuleHandleW(L"vulkan-1.dll");
    if (vk == nullptr) return false;

#define LOAD(name) p_##name = reinterpret_cast<PFN_##name>(GetProcAddress(vk, #name))
    LOAD(vkGetInstanceProcAddr);
    LOAD(vkCreateInstance);
    LOAD(vkEnumeratePhysicalDevices);
    LOAD(vkGetPhysicalDeviceProperties);
    LOAD(vkGetPhysicalDeviceMemoryProperties);
    LOAD(vkGetSwapchainImagesKHR);
    LOAD(vkCreateCommandPool);
    LOAD(vkDestroyCommandPool);
    LOAD(vkAllocateCommandBuffers);
    LOAD(vkCreateBuffer);
    LOAD(vkDestroyBuffer);
    LOAD(vkGetBufferMemoryRequirements);
    LOAD(vkAllocateMemory);
    LOAD(vkFreeMemory);
    LOAD(vkBindBufferMemory);
    LOAD(vkMapMemory);
    LOAD(vkUnmapMemory);
    LOAD(vkCreateFence);
    LOAD(vkDestroyFence);
    LOAD(vkResetFences);
    LOAD(vkWaitForFences);
    LOAD(vkBeginCommandBuffer);
    LOAD(vkEndCommandBuffer);
    LOAD(vkResetCommandBuffer);
    LOAD(vkCmdPipelineBarrier);
    LOAD(vkCmdCopyImageToBuffer);
    LOAD(vkQueueSubmit);
#undef LOAD

    if (!p_vkGetSwapchainImagesKHR || !p_vkCreateCommandPool || !p_vkAllocateCommandBuffers ||
        !p_vkCreateBuffer || !p_vkGetBufferMemoryRequirements || !p_vkAllocateMemory ||
        !p_vkBindBufferMemory || !p_vkMapMemory || !p_vkCreateFence || !p_vkWaitForFences ||
        !p_vkQueueSubmit || !p_vkCmdCopyImageToBuffer || !p_vkCreateInstance ||
        !p_vkGetPhysicalDeviceMemoryProperties) {
        hook_log("Vulkan: required entry points missing; not hooking");
        return false;
    }

    g_writer = writer;
    g_control = control;
    const uint32_t fps = (control && control->fps) ? control->fps : 30;
    g_frame_interval_us = 1000000ll / (fps ? fps : 30);

    bool ok = hook_one(vk, "vkQueuePresentKHR",
                       reinterpret_cast<LPVOID>(&d_vkQueuePresentKHR), &g_orig_vkQueuePresentKHR);
    ok &= hook_one(vk, "vkCreateSwapchainKHR",
                   reinterpret_cast<LPVOID>(&d_vkCreateSwapchainKHR), &g_orig_vkCreateSwapchainKHR);
    ok &= hook_one(vk, "vkDestroySwapchainKHR",
                   reinterpret_cast<LPVOID>(&d_vkDestroySwapchainKHR), &g_orig_vkDestroySwapchainKHR);
    // Queue→family mapping is best-effort (falls back to family 0), so failures here
    // are non-fatal.
    hook_one(vk, "vkGetDeviceQueue",
             reinterpret_cast<LPVOID>(&d_vkGetDeviceQueue), &g_orig_vkGetDeviceQueue);
    hook_one(vk, "vkGetDeviceQueue2",   // core 1.1; absent on older loaders
             reinterpret_cast<LPVOID>(&d_vkGetDeviceQueue2), &g_orig_vkGetDeviceQueue2);

    if (!ok) {
        hook_log("Vulkan hook: failed to install core hooks");
        return false;
    }
    hook_log("Vulkan hook installed (vkQueuePresentKHR + swapchain), fps=%u", fps);
    return true;
}

}  // namespace ambilight
