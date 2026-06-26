// shm_writer.cpp — see shm_writer.h.

#include "shm_writer.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <cstring>

namespace ambilight {

ShmWriter::~ShmWriter() { close(); }

bool ShmWriter::open(const std::wstring& name) {
    close();

    // Python created the mapping; we only attach to it.
    HANDLE h = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, name.c_str());
    if (h == nullptr) {
        last_error_ = "OpenFileMappingW failed (mapping not found); is the "
                      "Python owner alive?";
        return false;
    }

    // Map enough to read the ControlBlock first, then remap the full size.
    void* view = MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (view == nullptr) {
        CloseHandle(h);
        last_error_ = "MapViewOfFile failed";
        return false;
    }

    auto* ctrl = reinterpret_cast<ControlBlock*>(view);
    if (ctrl->magic != SHM_MAGIC) {
        UnmapViewOfFile(view);
        CloseHandle(h);
        last_error_ = "bad magic; mapping is not an ambilight frame buffer";
        return false;
    }
    if (ctrl->version != SHM_VERSION) {
        UnmapViewOfFile(view);
        CloseHandle(h);
        last_error_ = "protocol version mismatch between host and Python";
        return false;
    }
    if (ctrl->slot_count < 2 || ctrl->channels != 3) {
        UnmapViewOfFile(view);
        CloseHandle(h);
        last_error_ = "unsupported geometry (need >=2 slots, 3 channels)";
        return false;
    }

    handle_ = h;
    base_ = reinterpret_cast<uint8_t*>(view);
    ctrl_ = ctrl;
    mapped_size_ = shm_total_size(ctrl->slot_count, ctrl->slot_stride);
    frame_id_ = 0;
    last_error_.clear();
    return true;
}

void ShmWriter::close() {
    if (base_ != nullptr) {
        UnmapViewOfFile(base_);
        base_ = nullptr;
        ctrl_ = nullptr;
    }
    if (handle_ != nullptr) {
        CloseHandle(handle_);
        handle_ = nullptr;
    }
    mapped_size_ = 0;
}

SlotHeader* ShmWriter::slot_header(uint32_t index) {
    uint8_t* p = base_ + SHM_CONTROL_BLOCK_SIZE +
                 static_cast<uint64_t>(index) * ctrl_->slot_stride;
    return reinterpret_cast<SlotHeader*>(p);
}

uint8_t* ShmWriter::slot_pixels(uint32_t index) {
    return reinterpret_cast<uint8_t*>(slot_header(index)) + SHM_SLOT_HEADER_SIZE;
}

bool ShmWriter::write_frame(const uint8_t* pixels, uint32_t width,
                            uint32_t height, uint64_t timestamp_us) {
    if (base_ == nullptr || ctrl_ == nullptr) {
        last_error_ = "writer not open";
        return false;
    }
    if (width > ctrl_->max_width || height > ctrl_->max_height) {
        last_error_ = "frame exceeds buffer geometry";
        return false;
    }

    const uint32_t byte_size = width * height * ctrl_->channels;
    const uint32_t index = static_cast<uint32_t>(frame_id_ % ctrl_->slot_count);
    SlotHeader* hdr = slot_header(index);

    // Seqlock: each slot's seq starts even (Python zero-inits the buffer). One
    // increment makes it odd (write in progress); a second makes it even again
    // (stable). A reader sampling mid-write sees an odd seq and retries/skips.
    hdr->seq += 1u;  // even -> odd
    MemoryBarrier();

    std::memcpy(slot_pixels(index), pixels, byte_size);
    hdr->width = width;
    hdr->height = height;
    hdr->format = SHM_FORMAT_BGR;
    hdr->byte_size = byte_size;
    hdr->frame_id = frame_id_;
    hdr->timestamp_us = timestamp_us;

    MemoryBarrier();
    hdr->seq += 1u;  // odd -> even (stable)

    // Publish: make this the newest completed slot. Release-ordered atomic store
    // so the reader sees a fully-written slot before it sees the new index.
    InterlockedExchange64(reinterpret_cast<volatile LONG64*>(&ctrl_->latest_index),
                          static_cast<LONG64>(index));

    ++frame_id_;
    return true;
}

}  // namespace ambilight
