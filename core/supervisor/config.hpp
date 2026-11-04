#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace runbox::supervisor {

struct JobLimits {
    uint64_t timeout_ms = 3000;              // 3 seconds default
    uint64_t memory_mb = 128;                // 128 MB default
    uint32_t cpu_quota_percent = 50;         // 50% default
    uint32_t process_limit = 32;             // 32 processes default
    uint64_t output_limit_bytes = 1048576;   // 1 MB default
};

struct JobConfig {
    std::string execution_id;
    std::string language;                    // "python", "cpp", "minimal"
    std::string executable_path;             // e.g. "/usr/bin/python3"
    std::vector<std::string> argv;
    std::vector<std::string> env;
    std::string workspace_dir;
    std::string stdin_data;
    JobLimits limits;

    static JobConfig from_json(const std::string& json_str);
    std::string to_json() const;

    // Strict schema and security boundary validation (Section 3.2)
    [[nodiscard]] bool validate(std::string& err) const;
};

} // namespace runbox::supervisor
