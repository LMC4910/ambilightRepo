add_executable(capture_host
    main.cpp
    shm_writer.cpp
)

target_include_directories(capture_host PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/shared_memory
)

# Unicode entry point (wmain) + lean Windows headers.
target_compile_definitions(capture_host PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

# Phase 1 needs only the base Win32 API (kernel32, user32). DirectX libs come
# with graphics_hook in Phase 2.
