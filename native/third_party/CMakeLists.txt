# Vendored MinHook (https://github.com/TsudaKageyu/minhook, BSD-2-Clause), built
# as a static lib with the project's runtime/flags. Used for inline (trampoline)
# hooks where VMT hooking does not apply (Direct3D 9 / 12 have per-instance
# vtables, so only the shared function address can be hooked).
add_library(minhook STATIC
    minhook/src/buffer.c
    minhook/src/hook.c
    minhook/src/trampoline.c
    minhook/src/hde/hde32.c
    minhook/src/hde/hde64.c
)

target_include_directories(minhook PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/minhook/include)
target_include_directories(minhook PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/minhook/src)

if(MSVC)
    target_compile_definitions(minhook PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
