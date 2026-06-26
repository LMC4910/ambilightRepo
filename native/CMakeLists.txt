cmake_minimum_required(VERSION 3.20)

project(ambilight_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Statically link the MSVC runtime so the bundled helper has no dependency on the
# VC++ redistributable (VCRUNTIME140.dll / MSVCP140.dll) being installed on the
# end user's machine. Requires CMP0091 = NEW (default for cmake_minimum 3.20).
cmake_policy(SET CMP0091 NEW)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# MinGW / GCC fallback (when MSVC isn't the active toolchain): the Unicode entry
# point `wmain` requires -municode (otherwise the linker looks for WinMain), and
# we static-link libstdc++/libgcc/winpthread so the helper ships without MinGW
# runtime DLLs — matching the self-contained MSVC build above.
if(NOT MSVC)
    add_compile_options(-municode)
    add_link_options(-municode -static -static-libgcc -static-libstdc++)
endif()

# Default to a Release build when no config is given (single-config generators
# like Ninja). Multi-config generators (Visual Studio) ignore this and select
# the config at build time via --config.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

if(NOT WIN32)
    message(FATAL_ERROR "ambilight_native targets Windows only.")
endif()

# Phase 1: the fake-frame capture host. Phase 2 will add:
#   add_subdirectory(graphics_hook)
add_subdirectory(capture_host)
