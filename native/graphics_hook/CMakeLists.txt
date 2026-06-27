# graphics_hook.dll — injected into the target game; hooks Present and publishes
# frames into the Python-owned shared memory via the shared ambshm writer.
add_library(graphics_hook SHARED
    dllmain.cpp
    hooklog.cpp
    vmt_hook.cpp
    capture_util.cpp
    hook_dxgi.cpp
)

# No "lib" prefix on MinGW so the artifact is always graphics_hook.dll.
set_target_properties(graphics_hook PROPERTIES PREFIX "")

target_include_directories(graphics_hook PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(graphics_hook PRIVATE ambshm)

target_compile_definitions(graphics_hook PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

# DirectX import libs (DX9/10/11/12 + DXGI) ship with the Windows SDK.
target_link_libraries(graphics_hook PRIVATE d3d11 dxgi d3d9)
