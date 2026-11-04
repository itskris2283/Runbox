#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <chrono>
#include <optional>
#include <sys/types.h>
#include <unistd.h>

namespace runbox::process {

// RAII File Descriptor wrapper
class ScopedFd {
public:
    ScopedFd() noexcept : fd_(-1) {}
    explicit ScopedFd(int fd) noexcept : fd_(fd) {}
    ~ScopedFd() noexcept;

    ScopedFd(const ScopedFd&) = delete;
    ScopedFd& operator=(const ScopedFd&) = delete;

    ScopedFd(ScopedFd&& other) noexcept : fd_(other.fd_) {
        other.fd_ = -1;
    }

    ScopedFd& operator=(ScopedFd&& other) noexcept {
        if (this != &other) {
            reset(other.fd_);
            other.fd_ = -1;
        }
        return *this;
    }

    [[nodiscard]] int get() const noexcept { return fd_; }
    [[nodiscard]] bool valid() const noexcept { return fd_ >= 0; }
    int release() noexcept {
        int old_fd = fd_;
        fd_ = -1;
        return old_fd;
    }

    void reset(int new_fd = -1) noexcept;

private:
    int fd_;
};

// RAII Pipe wrapper (read_end and write_end)
class ScopedPipe {
public:
    ScopedPipe();
    ~ScopedPipe() = default;

    ScopedPipe(const ScopedPipe&) = delete;
    ScopedPipe& operator=(const ScopedPipe&) = delete;

    ScopedPipe(ScopedPipe&&) noexcept = default;
    ScopedPipe& operator=(ScopedPipe&&) noexcept = default;

    [[nodiscard]] int read_fd() const noexcept { return read_end_.get(); }
    [[nodiscard]] int write_fd() const noexcept { return write_end_.get(); }

    void close_read() noexcept { read_end_.reset(); }
    void close_write() noexcept { write_end_.reset(); }

    ScopedFd& reader() noexcept { return read_end_; }
    ScopedFd& writer() noexcept { return write_end_; }

private:
    ScopedFd read_end_;
    ScopedFd write_end_;
};

// Safe descriptor sanitization: close all file descriptors >= min_fd
void close_fds_except(const std::vector<int>& preserved_fds);

// Non-blocking read with byte limit
bool read_stream_bounded(int fd, std::string& buffer, size_t max_bytes, bool& truncated);

// Monotonic clock timing helper
[[nodiscard]] uint64_t get_monotonic_time_ms() noexcept;

} // namespace runbox::process
