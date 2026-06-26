// shm_protocol.h — canonical shared-memory layout for the hook capture transport.
//
// This header is the SINGLE SOURCE OF TRUTH for the wire format shared between
// the native capture host (writer) and the Python HookCaptureBackend (reader,
// in ambilight/hook_capture.py). Any change here MUST be mirrored in the Python
// struct definitions, and the version bumped.
//
// Layout (little-endian, tightly packed):
//
//   [ ControlBlock ]                         64 bytes, at offset 0
//   [ Slot 0 ][ Slot 1 ] ... [ Slot N-1 ]    each `slot_stride` bytes
//
//   Slot = [ SlotHeader (64 bytes) ][ raw BGR pixels ]
//
// Ownership: Python CREATES and OWNS the mapping (so a host crash never tears it
// down); the host ATTACHES via OpenFileMappingW. Python initialises the
// ControlBlock; the host reads geometry from it and writes slots.
//
// Concurrency: a single writer (host) and single reader (Python). The writer
// round-robins slots (slot = frame_id % slot_count) and publishes the newest
// completed slot via `latest_index`. Per-slot `seq` is a seqlock (odd = a write
// is in progress, even = stable) so the reader can detect a torn read. With
// slot_count >= 3 and a reader that keeps up, tearing is effectively impossible;
// the seqlock is belt-and-suspenders. Dropping frames is acceptable; blocking is
// not — the reader always takes the newest completed frame and never waits.

#ifndef AMBILIGHT_SHM_PROTOCOL_H
#define AMBILIGHT_SHM_PROTOCOL_H

#include <cstdint>

namespace ambilight {

// 'AMBH' little-endian == 0x484D4241. Lets the host reject a stale/foreign
// mapping before writing a single pixel.
constexpr uint32_t SHM_MAGIC = 0x484D4241u;
constexpr uint32_t SHM_VERSION = 1u;

// Pixel format codes (channels are always interleaved, 8-bit).
constexpr uint32_t SHM_FORMAT_BGR = 0u;  // 3 channels, B,G,R — matches CaptureBackend.grab()

constexpr uint32_t SHM_CONTROL_BLOCK_SIZE = 64u;
constexpr uint32_t SHM_SLOT_HEADER_SIZE = 64u;

// `latest_index` sentinel meaning "no frame published yet".
constexpr int64_t SHM_NO_FRAME = -1;

#pragma pack(push, 1)

// Fixed header at offset 0. Written once by Python on creation; `latest_index`
// is the only field mutated at runtime (by the host, atomically).
struct ControlBlock {
    uint32_t magic;        // SHM_MAGIC
    uint32_t version;      // SHM_VERSION
    uint32_t slot_count;   // number of ring slots (>= 2; we use 3)
    uint32_t max_width;    // max frame width the buffer was sized for
    uint32_t max_height;   // max frame height the buffer was sized for
    uint32_t channels;     // 3 for BGR
    uint32_t slot_stride;  // bytes per slot = SLOT_HEADER_SIZE + max pixel bytes
    uint32_t reserved0;    // padding so latest_index is 8-byte aligned
    int64_t  latest_index; // index of newest completed slot; SHM_NO_FRAME if none
    uint8_t  reserved1[24];// pad ControlBlock to 64 bytes
};

// Per-slot header, immediately followed by `byte_size` bytes of raw pixels.
struct SlotHeader {
    uint32_t seq;          // seqlock: odd = writing, even = stable
    uint32_t width;        // this frame's width
    uint32_t height;       // this frame's height
    uint32_t format;       // SHM_FORMAT_BGR
    uint32_t byte_size;    // pixel byte count = width * height * channels
    uint32_t reserved0;    // padding so frame_id is 8-byte aligned
    uint64_t frame_id;     // monotonically increasing frame counter
    uint64_t timestamp_us; // capture time, microseconds (host clock)
    uint8_t  reserved1[24];// pad SlotHeader to 64 bytes
};

#pragma pack(pop)

static_assert(sizeof(ControlBlock) == SHM_CONTROL_BLOCK_SIZE, "ControlBlock must be 64 bytes");
static_assert(sizeof(SlotHeader) == SHM_SLOT_HEADER_SIZE, "SlotHeader must be 64 bytes");

// Offsets the Python reader hard-codes — keep these assertions in sync.
static_assert(offsetof(ControlBlock, latest_index) == 32, "latest_index offset drift");
static_assert(offsetof(SlotHeader, frame_id) == 24, "frame_id offset drift");
static_assert(offsetof(SlotHeader, timestamp_us) == 32, "timestamp_us offset drift");

// Total mapping size for a given geometry. `slot_stride` already includes the
// header; both sides compute it identically.
inline uint64_t shm_total_size(uint32_t slot_count, uint32_t slot_stride) {
    return static_cast<uint64_t>(SHM_CONTROL_BLOCK_SIZE) +
           static_cast<uint64_t>(slot_count) * static_cast<uint64_t>(slot_stride);
}

}  // namespace ambilight

#endif  // AMBILIGHT_SHM_PROTOCOL_H
