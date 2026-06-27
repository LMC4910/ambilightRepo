# dx11_probe.exe — dev/test utility (not shipped). A minimal DX11 app used to
# exercise graphics_hook.dll without a real game.
add_executable(dx11_probe dx11_probe.cpp)

target_compile_definitions(dx11_probe PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

target_link_libraries(dx11_probe PRIVATE d3d11 dxgi)
