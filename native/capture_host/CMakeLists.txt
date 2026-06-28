add_executable(capture_host
    main.cpp
    inject.cpp
    detect.cpp
)

target_include_directories(capture_host PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Shared shm writer + protocol/control headers (its include dir comes transitively).
target_link_libraries(capture_host PRIVATE ambshm)

# Unicode entry point (wmain) + lean Windows headers.
target_compile_definitions(capture_host PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

# Phase 2 injection/detection: psapi for EnumProcessModulesEx/GetModuleBaseName.
target_link_libraries(capture_host PRIVATE psapi)
