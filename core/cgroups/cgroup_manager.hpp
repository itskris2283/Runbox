#pragma once

#include <cstdint>
#include <string>
#include <optional>
#include <sys/types.h>

namespace runbox::cgroups {

struct ResourceLimits {
    uint64_t memory_max_bytes = 128ULL * 1024ULL * 1024ULL; // 128 MB default
    uint64_t memory_swap_max_bytes = 0;                     // Disallow swap
    uint32_t cpu_quota_percent = 50;                        // 50% of 1 core default
    uint32_t cpu_period_us = 100000;                        // 100ms period
    uint32_t pids_max = 32;                                 // Max 32 processes
    bool enable_oom_group = true;                           // Kill entire group on OOM
};

struct ResourceUsage {
    uint64_t cpu_time_ms = 0;
    uint64_t memory_peak_bytes = 0;
    uint64_t memory_current_bytes = 0;
    uint32_t pids_peak = 0;
    uint32_t pids_current = 0;
    uint32_t oom_kill_count = 0;
    uint32_t oom_count = 0;
    uint32_t pids_max_events = 0;
    uint64_t nr_throttled = 0;
    bool oom_killed = false;
};

class CgroupManager {
public:
    explicit CgroupManager(std::string execution_id,
                           std::string base_cgroup_path = "/sys/fs/cgroup/runbox",
                           ResourceLimits limits = {});
    ~CgroupManager();

    CgroupManager(const CgroupManager&) = delete;
    CgroupManager& operator=(const CgroupManager&) = delete;
    CgroupManager(CgroupManager&&) noexcept;
    CgroupManager& operator=(CgroupManager&&) noexcept;

    // Creates the cgroup directory and applies configured limits
    bool initialize();

    // Attaches a target process PID to the cgroup
    bool add_process(pid_t pid);

    // Collects current and peak resource telemetry
    [[nodiscard]] ResourceUsage collect_usage() const;

    // Terminates all processes in the cgroup via cgroup.kill
    bool terminate_all(int timeout_ms = 1000);

    // Cleans up and deletes the cgroup directory
    bool destroy();

    [[nodiscard]] const std::string& get_cgroup_path() const noexcept { return cgroup_path_; }
    [[nodiscard]] bool is_initialized() const noexcept { return initialized_; }

private:
    std::string execution_id_;
    std::string base_path_;
    std::string cgroup_path_;
    ResourceLimits limits_;
    bool initialized_ = false;

    bool write_cgroup_file(const std::string& filename, const std::string& value);
    [[nodiscard]] std::string read_cgroup_file(const std::string& filename) const;
};

} // namespace runbox::cgroups
