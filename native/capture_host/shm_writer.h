// shm_writer.h — attaches to the Python-owned shared mapping and publishes
// frames into the ring buffer described by shared_memory/shm_protocol.h.
//
// The writer never creates the mapping; Python owns its lifetime. The writer
// only opens it (OpenFileMappingW), validates magic/version, and writes slots.

#ifndef AMBILIGHT_SHM_WRITER_H
#define AMBILIGHT_SHM_WRITER_H

#include <cstdint>
#include <string>

#include "shm_protocol.h"

namespace ambilight {

class ShmWriter {
public:
    ShmWriter() = default;
    ~ShmWriter();

    ShmWriter(const ShmWriter&) = delete;
    ShmWriter& operator=(const ShmWriter&) = delete;

    // Opens the named mapping created by Python and validates the ControlBlock.
    // Returns false (and sets last_error()) on any failure.
    bool open(const std::wstring& name);

    // Publishes one BGR frame. `pixels` points to width*height*3 bytes (BGR,
    // top-to-bottom, contiguous). Returns false if the frame exceeds the buffer
    // geometry or the writer is not open. Newest-frame-wins; never blocks.
    bool write_frame(const uint8_t* pixels, uint32_t width, uint32_t height,
                     uint64_t timestamp_us);

    bool is_open() const { return base_ != nullptr; }
    uint32_t max_width() const { return ctrl_ ? ctrl_->max_width : 0; }
    uint32_t max_height() const { return ctrl_ ? ctrl_->max_height : 0; }
    const std::string& last_error() const { return last_error_; }

    void close();

private:
    SlotHeader* slot_header(uint32_t index);
    uint8_t* slot_pixels(uint32_t index);

    void* handle_ = nullptr;       // HANDLE from OpenFileMappingW
    uint8_t* base_ = nullptr;      // MapViewOfFile base pointer
    ControlBlock* ctrl_ = nullptr; // == base_
    uint64_t mapped_size_ = 0;
    uint64_t frame_id_ = 0;
    std::string last_error_;
};

}  // namespace ambilight

#endif  // AMBILIGHT_SHM_WRITER_H
