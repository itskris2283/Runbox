#pragma once

#include "core/supervisor/config.hpp"
#include "core/monitoring/monitor.hpp"
#include "core/cgroups/cgroup_manager.hpp"
#include <string>

namespace runbox::supervisor {

class Supervisor {
public:
    Supervisor() = default;
    ~Supervisor() = default;

    // Executes a submitted job under full sandbox isolation and resource governance
    monitoring::ExecutionResult execute_job(const JobConfig& config,
                                            const std::string& base_cgroup_path = "/sys/fs/cgroup/runbox");

    // Modular child execution helpers (unit testable)
    static std::vector<std::string> prepare_argv(const JobConfig& config);
    static bool apply_child_security(const JobConfig& config);
    static void setup_child_io(int stdin_read_fd, int stdout_write_fd, int stderr_write_fd);
    static void assess_termination(int status, bool timed_out, const cgroups::ResourceUsage& usage, monitoring::ExecutionResult& result);

    void execute_child(const JobConfig& config,
                       int sync_c2p_write,
                       int sync_p2c_read,
                       int stdin_read_fd,
                       int stdout_write_fd,
                       int stderr_write_fd);
};

} // namespace runbox::supervisor
