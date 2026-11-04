#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <atomic>
#include <thread>
#include <chrono>

namespace runbox::monitoring {

enum class TerminationReason {
    NormalExit,
    NonZeroExit,
    TimedOut,
    MemoryLimitExceeded,
    ProcessLimitExceeded,
    OutputLimitExceeded,
    SecurityViolation,
    SignalTerminated,
    InternalError
};

std::string to_string(TerminationReason reason);

struct ExecutionResult {
    std::string execution_id;
    int exit_code = -1;
    TerminationReason reason = TerminationReason::InternalError;
    std::string stdout_output;
    std::string stderr_output;
    bool stdout_truncated = false;
    bool stderr_truncated = false;
    uint64_t stdout_bytes = 0;
    uint64_t stderr_bytes = 0;
    uint64_t wall_time_ms = 0;
    uint64_t cpu_time_ms = 0;
    uint64_t memory_peak_bytes = 0;
    uint32_t pids_peak = 0;
    bool oom_killed = false;
    std::string error_message;
};

class StreamConsumer {
public:
    StreamConsumer(int stdout_fd, int stderr_fd, size_t max_output_bytes);
    ~StreamConsumer();

    StreamConsumer(const StreamConsumer&) = delete;
    StreamConsumer& operator=(const StreamConsumer&) = delete;

    // Starts background reader threads consuming stdout and stderr concurrently to prevent pipe buffer deadlocks
    void start();

    // Waits for streams to close (EOF) or times out
    void wait_until_closed(int timeout_ms = 2000);

    // Stops reading
    void stop();

    [[nodiscard]] std::string get_stdout() const;
    [[nodiscard]] std::string get_stderr() const;
    [[nodiscard]] bool is_stdout_truncated() const noexcept { return stdout_truncated_; }
    [[nodiscard]] bool is_stderr_truncated() const noexcept { return stderr_truncated_; }
    [[nodiscard]] size_t get_stdout_bytes() const noexcept { return stdout_bytes_; }
    [[nodiscard]] size_t get_stderr_bytes() const noexcept { return stderr_bytes_; }

private:
    int stdout_fd_;
    int stderr_fd_;
    size_t max_output_bytes_;

    std::string stdout_buf_;
    std::string stderr_buf_;
    bool stdout_truncated_ = false;
    bool stderr_truncated_ = false;
    size_t stdout_bytes_ = 0;
    size_t stderr_bytes_ = 0;

    std::atomic<bool> running_{false};
    std::thread reader_thread_;

    void consume_loop();
};

} // namespace runbox::monitoring
