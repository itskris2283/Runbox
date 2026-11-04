#include "core/cgroups/cgroup_manager.hpp"

#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>
#include <fstream>
#include <sstream>
#include <iostream>
#include <thread>
#include <chrono>
#include <cstring>

namespace runbox::cgroups {

CgroupManager::CgroupManager(std::string execution_id,
                             std::string base_cgroup_path,
                             ResourceLimits limits)
    : execution_id_(std::move(execution_id)),
      base_path_(std::move(base_cgroup_path)),
      cgroup_path_(base_path_ + "/" + execution_id_),
      limits_(limits),
      initialized_(false) {}

CgroupManager::~CgroupManager() {
    if (initialized_) {
        terminate_all(50);
        destroy();
    }
}

CgroupManager::CgroupManager(CgroupManager&& other) noexcept
    : execution_id_(std::move(other.execution_id_)),
      base_path_(std::move(other.base_path_)),
      cgroup_path_(std::move(other.cgroup_path_)),
      limits_(other.limits_),
      initialized_(other.initialized_) {
    other.initialized_ = false;
}

CgroupManager& CgroupManager::operator=(CgroupManager&& other) noexcept {
    if (this != &other) {
        if (initialized_) {
            terminate_all(500);
            destroy();
        }
        execution_id_ = std::move(other.execution_id_);
        base_path_ = std::move(other.base_path_);
        cgroup_path_ = std::move(other.cgroup_path_);
        limits_ = other.limits_;
        initialized_ = other.initialized_;
        other.initialized_ = false;
    }
    return *this;
}

bool CgroupManager::write_cgroup_file(const std::string& filename, const std::string& value) {
    std::string path = cgroup_path_ + "/" + filename;
    std::ofstream file(path);
    if (!file.is_open()) {
        std::cerr << "[runbox::cgroups] failed to open for writing: " << path << " (" << strerror(errno) << ")\n";
        return false;
    }
    file << value << "\n";
    if (file.fail()) {
        std::cerr << "[runbox::cgroups] failed to write to: " << path << " (" << strerror(errno) << ")\n";
        return false;
    }
    return true;
}

std::string CgroupManager::read_cgroup_file(const std::string& filename) const {
    std::string path = cgroup_path_ + "/" + filename;
    std::ifstream file(path);
    if (!file.is_open()) {
        return "";
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

bool CgroupManager::initialize() {
    // 1. Ensure base cgroup exists and has subtree control enabled
    ::mkdir(base_path_.c_str(), 0755);
    std::string base_subtree = base_path_ + "/cgroup.subtree_control";
    {
        std::ofstream st(base_subtree);
        if (st.is_open()) {
            st << "+memory +cpu +pids\n";
            st.close();
        }
    }

    // 2. Create execution cgroup directory
    if (::mkdir(cgroup_path_.c_str(), 0755) != 0) {
        if (errno != EEXIST) {
            std::cerr << "[runbox::cgroups] failed to create cgroup directory: " << cgroup_path_
                      << " (" << strerror(errno) << ")\n";
            return false;
        }
    }

    // 3. Configure memory limit
    if (limits_.memory_max_bytes > 0) {
        if (!write_cgroup_file("memory.max", std::to_string(limits_.memory_max_bytes))) {
            destroy();
            return false;
        }
        std::string mem_check = read_cgroup_file("memory.max");
        if (mem_check.empty()) {
            std::cerr << "[runbox::cgroups] failed to read back memory.max configuration\n";
            destroy();
            return false;
        }
    }

    // Disable swap where supported
    write_cgroup_file("memory.swap.max", std::to_string(limits_.memory_swap_max_bytes));

    // Enable memory.oom.group if configured
    if (limits_.enable_oom_group) {
        write_cgroup_file("memory.oom.group", "1");
    }

    // 4. Configure CPU quota
    if (limits_.cpu_quota_percent > 0) {
        uint64_t quota_us = (static_cast<uint64_t>(limits_.cpu_period_us) * limits_.cpu_quota_percent) / 100ULL;
        std::string cpu_max_val = std::to_string(quota_us) + " " + std::to_string(limits_.cpu_period_us);
        if (!write_cgroup_file("cpu.max", cpu_max_val)) {
            destroy();
            return false;
        }
    }

    // 5. Configure PIDs limit
    if (limits_.pids_max > 0) {
        if (!write_cgroup_file("pids.max", std::to_string(limits_.pids_max))) {
            destroy();
            return false;
        }
        std::string pids_check = read_cgroup_file("pids.max");
        if (pids_check.empty()) {
            std::cerr << "[runbox::cgroups] failed to read back pids.max configuration\n";
            destroy();
            return false;
        }
    }

    initialized_ = true;
    return true;
}

bool CgroupManager::add_process(pid_t pid) {
    if (!initialized_) return false;
    return write_cgroup_file("cgroup.procs", std::to_string(pid));
}

ResourceUsage CgroupManager::collect_usage() const {
    ResourceUsage usage{};
    if (!initialized_) return usage;

    // Read memory peak and current
    std::string mem_peak_str = read_cgroup_file("memory.peak");
    if (!mem_peak_str.empty()) {
        try { usage.memory_peak_bytes = std::stoull(mem_peak_str); } catch (...) {}
    }

    std::string mem_curr_str = read_cgroup_file("memory.current");
    if (!mem_curr_str.empty()) {
        try {
            usage.memory_current_bytes = std::stoull(mem_curr_str);
            if (usage.memory_peak_bytes == 0) {
                usage.memory_peak_bytes = usage.memory_current_bytes;
            }
        } catch (...) {}
    }

    // Read memory events (OOM)
    std::string mem_events = read_cgroup_file("memory.events");
    if (!mem_events.empty()) {
        std::istringstream stream(mem_events);
        std::string key;
        uint32_t val;
        while (stream >> key >> val) {
            if (key == "oom") usage.oom_count = val;
            else if (key == "oom_kill") usage.oom_kill_count = val;
        }
    }
    if (usage.oom_kill_count > 0 || usage.oom_count > 0) {
        usage.oom_killed = true;
    }

    // Read CPU stat
    std::string cpu_stat = read_cgroup_file("cpu.stat");
    if (!cpu_stat.empty()) {
        std::istringstream stream(cpu_stat);
        std::string key;
        uint64_t val;
        while (stream >> key >> val) {
            if (key == "usage_usec") usage.cpu_time_ms = val / 1000ULL;
            else if (key == "nr_throttled") usage.nr_throttled = val;
        }
    }

    // Read PIDs
    std::string pids_curr_str = read_cgroup_file("pids.current");
    if (!pids_curr_str.empty()) {
        try { usage.pids_current = static_cast<uint32_t>(std::stoul(pids_curr_str)); } catch (...) {}
    }

    std::string pids_peak_str = read_cgroup_file("pids.peak");
    if (!pids_peak_str.empty()) {
        try { usage.pids_peak = static_cast<uint32_t>(std::stoul(pids_peak_str)); } catch (...) {}
    }

    std::string pids_events = read_cgroup_file("pids.events");
    if (!pids_events.empty()) {
        std::istringstream stream(pids_events);
        std::string key;
        uint32_t val;
        while (stream >> key >> val) {
            if (key == "max") usage.pids_max_events = val;
        }
    }

    return usage;
}

bool CgroupManager::terminate_all(int timeout_ms) {
    if (!initialized_) return true;

    // Use cgroup.kill (Linux 5.14+) for atomic group termination
    write_cgroup_file("cgroup.kill", "1");

    auto start = std::chrono::steady_clock::now();
    while (true) {
        std::string procs = read_cgroup_file("cgroup.procs");
        if (procs.empty() || procs.find_first_not_of(" \t\n\r") == std::string::npos) {
            return true; // All processes terminated cleanly
        }

        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start).count();
        if (elapsed > timeout_ms) {
            // Fallback: manually kill each remaining PID
            std::istringstream stream(procs);
            pid_t pid;
            while (stream >> pid) {
                if (pid > 1) {
                    ::kill(pid, SIGKILL);
                }
            }
            break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    return true;
}

bool CgroupManager::destroy() {
    if (cgroup_path_.empty()) return true;
    for (int retry = 0; retry < 5; ++retry) {
        int res = ::rmdir(cgroup_path_.c_str());
        if (res == 0) {
            initialized_ = false;
            return true;
        }
        if (errno != EBUSY) break;
        ::usleep(1000);
    }
    return false;
}

} // namespace runbox::cgroups
