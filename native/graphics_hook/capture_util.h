// capture_util.h — pixel-format conversion shared by the per-API hooks.
//
// Converts a mapped GPU surface (which may have a row pitch larger than
// width*bpp) into a tightly-packed BGR buffer the ShmWriter expects.

#ifndef AMBILIGHT_CAPTURE_UTIL_H
#define AMBILIGHT_CAPTURE_UTIL_H

#include <cstdint>
#include <vector>

#include <dxgiformat.h>

namespace ambilight {

// Convert a DXGI-format mapped surface to packed BGR (w*h*3) in *out*.
// Honors *row_pitch*. Returns false for unsupported formats (10-bit/HDR, etc.).
bool dxgi_to_bgr(const uint8_t* src, int row_pitch, uint32_t width, uint32_t height,
                 DXGI_FORMAT format, std::vector<uint8_t>& out);

// Convert a D3D9 mapped surface (D3DFMT_* given as a FourCC/enum int) to packed
// BGR. Supports the common X8R8G8B8 / A8R8G8B8 backbuffer formats (which are BGRA
// in memory). Returns false otherwise.
bool d3d9_to_bgr(const uint8_t* src, int row_pitch, uint32_t width, uint32_t height,
                 uint32_t d3dformat, std::vector<uint8_t>& out);

}  // namespace ambilight

#endif  // AMBILIGHT_CAPTURE_UTIL_H
