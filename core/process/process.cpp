#include "core/process/process.hpp"

#include <fcntl.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <dirent.h>
#include <cerrno>
#include <cstring>
#include <algorithm>
#include <stdexcept>

namespace runbox::process {

ScopedFd::~ScopedFd() noexcept {
    reset();
}

void ScopedFd::reset(int new_fd) noexcept {
    if (fd_ >= 0) {
        ::close(fd_);
    }
    fd_ = new_fd;
}

ScopedPipe::ScopedPipe() {
    int pipe_fds[2] = {-1, -1};
#if defined(O_CLOEXEC)
    if (::pipe2(pipe_fds, O_CLOEXEC) != 0) {
        throw std::runtime_error("pipe2(O_CLOEXEC) failed: " + std::string(strerror(errno)));
    }
#else
    if (::pipe(pipe_fds) != 0) {
        throw std::runtime_error("pipe failed: " + std::string(strerror(errno)));
    }
    ::fcntl(pipe_fds[0], F_SETFD, FD_CLOEXEC);
    ::fcntl(pipe_fds[1], F_SETFD, FD_CLOEXEC);
#endif
    read_end_.reset(pipe_fds[0]);
    write_end_.reset(pipe_fds[1]);
}

void close_fds_except(const std::vector<int>& preserved_fds) {
    // Try close_range syscall first (available Linux 5.9+)
#if defined(SYS_close_range)
    // For close_range, we can close from 3 to ~0U, but we must preserve our specific FDs
    // If preserved list is small, we can sort it and call close_range on ranges
    std::vector<int> sorted_preserved = preserved_fds;
    std::sort(sorted_preserved.begin(), sorted_preserved.end());

    int current_first = 3;
    for (int pfd : sorted_preserved) {
        if (pfd < 3) continue;
        if (pfd > current_first) {
            ::syscall(SYS_close_range, static_cast<unsigned int>(current_first), static_cast<unsigned int>(pfd - 1), 0);
        }
        current_first = pfd + 1;
    }
    ::syscall(SYS_close_range, static_cast<unsigned int>(current_first), ~0U, 0);
#else
    // Fallback: enumerate /proc/self/fd
    DIR* dir = ::opendir("/proc/self/fd");
    if (dir != nullptr) {
        int dir_fd = ::dirfd(dir);
        struct dirent* entry = nullptr;
        while ((entry = ::readdir(dir)) != nullptr) {
            if (entry->d_name[0] == '.') continue;
            int fd = std::atoi(entry->d_name);
            if (fd >= 3 && fd != dir_fd) {
                if (std::find(preserved_fds.begin(), preserved_fds.end(), fd) == preserved_fds.end()) {
                    ::close(fd);
                }
            }
        }
        ::closedir(dir);
    } else {
        // Last-resort fallback: sysconf(_SC_OPEN_MAX)
        int max_fd = static_cast<int>(::sysconf(_SC_OPEN_MAX));
        if (max_fd < 0 || max_fd > 65536) max_fd = 1024;
        for (int fd = 3; fd < max_fd; ++fd) {
            if (std::find(preserved_fds.begin(), preserved_fds.end(), fd) == preserved_fds.end()) {
                ::close(fd);
            }
        }
    }
#endif
}

bool read_stream_bounded(int fd, std::string& buffer, size_t max_bytes, bool& truncated) {
    if (fd < 0) return false;

    char chunk[4096];
    while (true) {
        ssize_t bytes_read = ::read(fd, chunk, sizeof(chunk));
        if (bytes_read > 0) {
            size_t count = static_cast<size_t>(bytes_read);
            if (buffer.size() + count > max_bytes) {
                size_t allowed = max_bytes > buffer.size() ? max_bytes - buffer.size() : 0;
                buffer.append(chunk, allowed);
                truncated = true;
                // Discard further incoming data until EOF
            } else {
                buffer.append(chunk, count);
            }
        } else if (bytes_read == 0) {
            // EOF reached
            break;
        } else {
            if (errno == EINTR) continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Non-blocking read finished for now
                break;
            }
            return false;
        }
    }
    return true;
}

uint64_t get_monotonic_time_ms() noexcept {
    struct timespec ts{};
    ::clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<uint64_t>(ts.tv_sec) * 1000ULL +
           static_cast<uint64_t>(ts.tv_nsec) / 1000000ULL;
}

} // namespace runbox::process
