# ambshm: the shared-memory writer + protocol/control headers, shared by both
# capture_host.exe and graphics_hook.dll so they speak the exact same wire format.
add_library(ambshm STATIC shm_writer.cpp)

target_include_directories(ambshm PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

target_compile_definitions(ambshm PUBLIC
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)
