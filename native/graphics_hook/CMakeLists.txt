# graphics_hook.dll — injected into the target game; hooks Present and publishes
# frames into the Python-owned shared memory via the shared ambshm writer.
add_library(graphics_hook SHARED
    dllmain.cpp
    hooklog.cpp
    vmt_hook.cpp
    capture_util.cpp
    hook_dxgi.cpp
    hook_d3d9.cpp
)

# No "lib" prefix on MinGW so the artifact is always graphics_hook.dll.
set_target_properties(graphics_hook PROPERTIES PREFIX "")

target_include_directories(graphics_hook PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(graphics_hook PRIVATE ambshm minhook)

target_compile_definitions(graphics_hook PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

# NOTE: no link-time DirectX libs. The DX create functions (D3D11CreateDeviceAndSwapChain,
# Direct3DCreate9, …) are resolved at runtime via GetProcAddress from the modules the
# game already loaded, so injecting into any game forces no extra D3D DLLs to load.
# DirectX COM interface declarations come from the SDK headers (d3d9/10/11/12.h, dxgi.h).
