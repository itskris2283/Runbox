#include "core/monitoring/monitor.hpp"

#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <iostream>

namespace runbox::monitoring {

std::string to_string(TerminationReason reason) {
    switch (reason) {
        case TerminationReason::NormalExit:          return "normal_exit";
        case TerminationReason::NonZeroExit:        return "non_zero_exit";
        case TerminationReason::TimedOut:           return "timed_out";
        case TerminationReason::MemoryLimitExceeded: return "memory_limit_exceeded";
        case TerminationReason::ProcessLimitExceeded:return "process_limit_exceeded";
        case TerminationReason::OutputLimitExceeded: return "output_limit_exceeded";
        case TerminationReason::SecurityViolation:   return "security_violation";
        case TerminationReason::SignalTerminated:    return "signal_terminated";
        case TerminationReason::InternalError:       return "internal_error";
    }
    return "unknown";
}

StreamConsumer::StreamConsumer(int stdout_fd, int stderr_fd, size_t max_output_bytes)
    : stdout_fd_(stdout_fd),
      stderr_fd_(stderr_fd),
      max_output_bytes_(max_output_bytes) {}

StreamConsumer::~StreamConsumer() {
    stop();
}

void StreamConsumer::start() {
    running_ = true;
    reader_thread_ = std::thread(&StreamConsumer::consume_loop, this);
}

void StreamConsumer::wait_until_closed(int timeout_ms) {
    if (reader_thread_.joinable()) {
        auto start = std::chrono::steady_clock::now();
        while (running_) {
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start).count();
            if (elapsed > timeout_ms) {
                stop();
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        if (reader_thread_.joinable()) {
            reader_thread_.join();
        }
    }
}

void StreamConsumer::stop() {
    running_ = false;
    if (reader_thread_.joinable()) {
        reader_thread_.join();
    }
}

std::string StreamConsumer::get_stdout() const {
    return stdout_buf_;
}

std::string StreamConsumer::get_stderr() const {
    return stderr_buf_;
}

void StreamConsumer::consume_loop() {
    struct pollfd fds[2];
    fds[0].fd = stdout_fd_;
    fds[0].events = POLLIN | POLLHUP | POLLERR;
    fds[1].fd = stderr_fd_;
    fds[1].events = POLLIN | POLLHUP | POLLERR;

    bool stdout_open = (stdout_fd_ >= 0);
    bool stderr_open = (stderr_fd_ >= 0);

    char chunk[4096];

    while (running_ && (stdout_open || stderr_open)) {
        int active_fds = 0;
        if (stdout_open) { fds[0].fd = stdout_fd_; active_fds++; } else { fds[0].fd = -1; }
        if (stderr_open) { fds[1].fd = stderr_fd_; active_fds++; } else { fds[1].fd = -1; }

        int ret = ::poll(fds, 2, 10); // 10ms poll interval
        if (ret < 0) {
            if (errno == EINTR) continue;
            break;
        }

        // Process stdout
        if (stdout_open && (fds[0].revents & (POLLIN | POLLHUP | POLLERR))) {
            ssize_t bytes = ::read(stdout_fd_, chunk, sizeof(chunk));
            if (bytes > 0) {
                size_t count = static_cast<size_t>(bytes);
                stdout_bytes_ += count;
                if (stdout_buf_.size() < max_output_bytes_) {
                    size_t space = max_output_bytes_ - stdout_buf_.size();
                    size_t to_append = std::min(count, space);
                    stdout_buf_.append(chunk, to_append);
                }
                if (stdout_bytes_ > max_output_bytes_) {
                    stdout_truncated_ = true;
                }
            } else if (bytes == 0 || (bytes < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                stdout_open = false;
            }
        }

        // Process stderr
        if (stderr_open && (fds[1].revents & (POLLIN | POLLHUP | POLLERR))) {
            ssize_t bytes = ::read(stderr_fd_, chunk, sizeof(chunk));
            if (bytes > 0) {
                size_t count = static_cast<size_t>(bytes);
                stderr_bytes_ += count;
                if (stderr_buf_.size() < max_output_bytes_) {
                    size_t space = max_output_bytes_ - stderr_buf_.size();
                    size_t to_append = std::min(count, space);
                    stderr_buf_.append(chunk, to_append);
                }
                if (stderr_bytes_ > max_output_bytes_) {
                    stderr_truncated_ = true;
                }
            } else if (bytes == 0 || (bytes < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                stderr_open = false;
            }
        }
    }

    running_ = false;
}

} // namespace runbox::monitoring
