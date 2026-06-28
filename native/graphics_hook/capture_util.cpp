// capture_util.cpp — see capture_util.h.

#include "capture_util.h"

namespace ambilight {

namespace {

// BGRA in memory -> BGR (drop alpha). Used for B8G8R8A8 (DXGI) and the D3D9
// X8R8G8B8 / A8R8G8B8 backbuffer formats (also B,G,R,A byte order).
void pack_bgra(const uint8_t* src, int row_pitch, uint32_t w, uint32_t h,
               std::vector<uint8_t>& out) {
    out.resize(static_cast<size_t>(w) * h * 3u);
    uint8_t* dst = out.data();
    for (uint32_t y = 0; y < h; ++y) {
        const uint8_t* row = src + static_cast<size_t>(y) * row_pitch;
        for (uint32_t x = 0; x < w; ++x) {
            const uint8_t* p = row + x * 4u;
            *dst++ = p[0];  // B
            *dst++ = p[1];  // G
            *dst++ = p[2];  // R
        }
    }
}

// RGBA in memory -> BGR (swap R/B). Used for R8G8B8A8 (DXGI).
void pack_rgba(const uint8_t* src, int row_pitch, uint32_t w, uint32_t h,
               std::vector<uint8_t>& out) {
    out.resize(static_cast<size_t>(w) * h * 3u);
    uint8_t* dst = out.data();
    for (uint32_t y = 0; y < h; ++y) {
        const uint8_t* row = src + static_cast<size_t>(y) * row_pitch;
        for (uint32_t x = 0; x < w; ++x) {
            const uint8_t* p = row + x * 4u;
            *dst++ = p[2];  // B
            *dst++ = p[1];  // G
            *dst++ = p[0];  // R
        }
    }
}

}  // namespace

bool dxgi_to_bgr(const uint8_t* src, int row_pitch, uint32_t width, uint32_t height,
                 DXGI_FORMAT format, std::vector<uint8_t>& out) {
    if (src == nullptr || width == 0 || height == 0) return false;
    switch (format) {
        case DXGI_FORMAT_B8G8R8A8_UNORM:
        case DXGI_FORMAT_B8G8R8A8_UNORM_SRGB:
        case DXGI_FORMAT_B8G8R8X8_UNORM:
        case DXGI_FORMAT_B8G8R8X8_UNORM_SRGB:
            pack_bgra(src, row_pitch, width, height, out);
            return true;
        case DXGI_FORMAT_R8G8B8A8_UNORM:
        case DXGI_FORMAT_R8G8B8A8_UNORM_SRGB:
            pack_rgba(src, row_pitch, width, height, out);
            return true;
        default:
            // 10-bit HDR (R10G10B10A2), float backbuffers, etc. — out of scope (SDR).
            return false;
    }
}

// D3DFORMAT values we care about (avoid pulling in d3d9.h here).
//   D3DFMT_A8R8G8B8 = 21, D3DFMT_X8R8G8B8 = 22  — both B,G,R,A in memory.
bool d3d9_to_bgr(const uint8_t* src, int row_pitch, uint32_t width, uint32_t height,
                 uint32_t d3dformat, std::vector<uint8_t>& out) {
    if (src == nullptr || width == 0 || height == 0) return false;
    switch (d3dformat) {
        case 21:  // D3DFMT_A8R8G8B8
        case 22:  // D3DFMT_X8R8G8B8
            pack_bgra(src, row_pitch, width, height, out);
            return true;
        default:
            return false;
    }
}

}  // namespace ambilight
