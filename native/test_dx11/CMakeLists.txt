# Dev/test utilities (not shipped). Minimal DX11 / DX9 apps used to exercise
# graphics_hook.dll without a real game.
add_executable(dx11_probe dx11_probe.cpp)
target_compile_definitions(dx11_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(dx11_probe PRIVATE d3d11 dxgi)

add_executable(dx9_probe dx9_probe.cpp)
target_compile_definitions(dx9_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(dx9_probe PRIVATE d3d9)

add_executable(dx12_probe dx12_probe.cpp)
target_compile_definitions(dx12_probe PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(dx12_probe PRIVATE d3d12 dxgi)
