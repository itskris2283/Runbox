#include "core/supervisor/supervisor.hpp"
#include "core/process/process.hpp"
#include "core/namespaces/namespaces.hpp"
#include "core/cgroups/cgroup_manager.hpp"
#include "core/seccomp/seccomp_rules.hpp"
#include "core/filesystem/filesystem_isolation.hpp"
#include "core/security/privileges.hpp"

#include <sys/wait.h>
#include <sys/signalfd.h>
#include <sys/timerfd.h>
#include <sys/prctl.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <cstring>
#include <iostream>
#include <thread>
#include <chrono>
#include <filesystem>

#ifdef RUNBOX_ENABLE_COVERAGE
extern "C" void __gcov_dump(void);
#endif

namespace runbox::supervisor {

static void ignore_io_result(ssize_t result) {
    (void)result;
}

monitoring::ExecutionResult Supervisor::execute_job(const JobConfig& config,
                                                    const std::string& base_cgroup_path) {
    monitoring::ExecutionResult result;
    result.execution_id = config.execution_id;
    uint64_t start_time = process::get_monotonic_time_ms();

    // 1. Prepare dedicated Cgroup v2
    cgroups::ResourceLimits cgroup_limits;
    cgroup_limits.memory_max_bytes = config.limits.memory_mb * 1024ULL * 1024ULL;
    cgroup_limits.cpu_quota_percent = config.limits.cpu_quota_percent;
    cgroup_limits.pids_max = config.limits.process_limit;
    cgroups::CgroupManager cgroup(config.execution_id, base_cgroup_path, cgroup_limits);

    if (!cgroup.initialize()) {
        std::cerr << "[runbox::supervisor] warning: cgroup initialization failed, proceeding with rlimits defense\n";
    }

    // 2. Prepare synchronization and I/O pipes
    process::ScopedPipe sync_c2p;   // Child -> Parent: child unshared
    process::ScopedPipe sync_p2c;   // Parent -> Child: parent assigned cgroup & uid_map
    process::ScopedPipe stdout_pipe;
    process::ScopedPipe stderr_pipe;
    process::ScopedPipe stdin_pipe;

    // Block SIGCHLD before fork so child exit signals are queued for signalfd
    sigset_t chld_mask, orig_mask;
    sigemptyset(&chld_mask);
    sigaddset(&chld_mask, SIGCHLD);
    ::sigprocmask(SIG_BLOCK, &chld_mask, &orig_mask);

    pid_t parent_pid = ::getpid();
    pid_t pid = ::fork();
    if (pid < 0) {
        ::sigprocmask(SIG_SETMASK, &orig_mask, nullptr);
        result.reason = monitoring::TerminationReason::InternalError;
        result.error_message = "fork() failed: " + std::string(strerror(errno));
        return result;
    }

    if (pid == 0) {
        // --- CHILD PROCESS ---
        // Ensure child dies immediately if parent supervisor process terminates unexpectedly
        ::prctl(PR_SET_PDEATHSIG, SIGKILL);
        if (::getppid() != parent_pid) {
            ::_exit(1);
        }
        ::sigprocmask(SIG_SETMASK, &orig_mask, nullptr);
        sync_c2p.close_read();
        sync_p2c.close_write();
        stdout_pipe.close_read();
        stderr_pipe.close_read();
        stdin_pipe.close_write();

        execute_child(config,
                      sync_c2p.write_fd(),
                      sync_p2c.read_fd(),
                      stdin_pipe.read_fd(),
                      stdout_pipe.write_fd(),
                      stderr_pipe.write_fd());
#ifdef RUNBOX_ENABLE_COVERAGE
        __gcov_dump();
#endif
        ::_exit(127);
    }

    // --- PARENT / SUPERVISOR PROCESS ---
    sync_c2p.close_write();
    sync_p2c.close_read();
    stdout_pipe.close_write();
    stderr_pipe.close_write();
    stdin_pipe.close_read();

    // Wait for child to initialize namespaces
    char sync_byte = 0;
    ssize_t r = ::read(sync_c2p.read_fd(), &sync_byte, 1);
    if (r <= 0) {
        int status = 0;
        ::waitpid(pid, &status, 0);
        result.reason = monitoring::TerminationReason::InternalError;
        result.error_message = "Child failed during initial sandbox setup";
        cgroup.destroy();
        return result;
    }

    // Assign child process to dedicated cgroup
    if (cgroup.is_initialized()) {
        cgroup.add_process(pid);
    }

    // Map unprivileged user ID to root (UID 0) inside sandbox user namespace
    namespaces::NamespaceManager::write_id_mappings(pid, ::getuid(), ::getgid(), 0, 0);

    // Release child to proceed with mount setup, privilege dropping, and execve
    char release_byte = 1;
    ignore_io_result(::write(sync_p2c.write_fd(), &release_byte, 1));
    sync_p2c.close_write();

    // Deliver stdin data if present
    if (!config.stdin_data.empty()) {
        ignore_io_result(::write(stdin_pipe.write_fd(), config.stdin_data.data(), config.stdin_data.size()));
    }
    stdin_pipe.close_write();

    // Start streaming consumer for stdout and stderr to prevent pipe buffer deadlocks
    monitoring::StreamConsumer consumer(stdout_pipe.read_fd(),
                                        stderr_pipe.read_fd(),
                                        config.limits.output_limit_bytes);
    consumer.start();

    // 1. Setup timerfd for kernel monotonic deadline enforcement
    int tfd = ::timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
    if (tfd >= 0) {
        struct itimerspec its{};
        its.it_value.tv_sec = static_cast<time_t>(config.limits.timeout_ms / 1000);
        its.it_value.tv_nsec = static_cast<long>((config.limits.timeout_ms % 1000) * 1000000ULL);
        ::timerfd_settime(tfd, 0, &its, nullptr);
    }

    // 2. Setup signalfd for zero-delay child process exit notification
    int sfd = ::signalfd(-1, &chld_mask, SFD_NONBLOCK | SFD_CLOEXEC);

    // Execution monitor loop with monotonic deadline
    bool timed_out = false;
    int status = 0;
    uint64_t termination_wall_time = 0;

    struct pollfd pfds[2];
    int nfds = 0;
    if (sfd >= 0) {
        pfds[nfds].fd = sfd;
        pfds[nfds].events = POLLIN;
        pfds[nfds].revents = 0;
        nfds++;
    }
    if (tfd >= 0) {
        pfds[nfds].fd = tfd;
        pfds[nfds].events = POLLIN;
        pfds[nfds].revents = 0;
        nfds++;
    }

    while (true) {
        pid_t w = ::waitpid(pid, &status, WNOHANG);
        if (w == pid) {
            termination_wall_time = process::get_monotonic_time_ms() - start_time;
            break;
        }

        uint64_t elapsed = process::get_monotonic_time_ms() - start_time;
        if (tfd < 0 && elapsed >= config.limits.timeout_ms) {
            timed_out = true;
            termination_wall_time = elapsed;
            if (cgroup.is_initialized()) {
                cgroup.terminate_all(50);
            }
            ::kill(pid, SIGKILL);
            ::waitpid(pid, &status, 0);
            break;
        }

        uint64_t remaining_ms = (elapsed < config.limits.timeout_ms) ? (config.limits.timeout_ms - elapsed) : 0;
        int poll_timeout = (tfd >= 0) ? static_cast<int>(std::min(remaining_ms + 50, uint64_t{100})) : static_cast<int>(std::min(remaining_ms, uint64_t{10}));

        int ret = (nfds > 0) ? ::poll(pfds, static_cast<nfds_t>(nfds), poll_timeout) : 0;
        if (ret > 0) {
            for (int i = 0; i < nfds; ++i) {
                if (pfds[i].fd == tfd && (pfds[i].revents & POLLIN)) {
                    uint64_t expirations = 0;
                    ssize_t s = ::read(tfd, &expirations, sizeof(expirations));
                    (void)s;
                    // Timerfd expired: check if child exited right at deadline
                    w = ::waitpid(pid, &status, WNOHANG);
                    if (w == pid) {
                        termination_wall_time = process::get_monotonic_time_ms() - start_time;
                        timed_out = (termination_wall_time >= config.limits.timeout_ms);
                    } else {
                        timed_out = true;
                        termination_wall_time = process::get_monotonic_time_ms() - start_time;
                        if (cgroup.is_initialized()) {
                            cgroup.terminate_all(50);
                        }
                        ::kill(pid, SIGKILL);
                        ::waitpid(pid, &status, 0);
                    }
                    goto loop_exit;
                }
                if (pfds[i].fd == sfd && (pfds[i].revents & POLLIN)) {
                    struct signalfd_siginfo fdsi{};
                    ssize_t s = ::read(sfd, &fdsi, sizeof(fdsi));
                    (void)s;
                    w = ::waitpid(pid, &status, WNOHANG);
                    if (w == pid) {
                        termination_wall_time = process::get_monotonic_time_ms() - start_time;
                        goto loop_exit;
                    }
                }
            }
        } else if (nfds == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }

loop_exit:
    if (tfd >= 0) ::close(tfd);
    if (sfd >= 0) {
        ::close(sfd);
    }
    ::sigprocmask(SIG_SETMASK, &orig_mask, nullptr);

    if (termination_wall_time == 0) {
        termination_wall_time = process::get_monotonic_time_ms() - start_time;
    }
    result.wall_time_ms = termination_wall_time;

    // Drain output streams
    consumer.wait_until_closed(500);

    // Collect telemetry
    result.stdout_output = consumer.get_stdout();
    result.stderr_output = consumer.get_stderr();
    result.stdout_truncated = consumer.is_stdout_truncated();
    result.stderr_truncated = consumer.is_stderr_truncated();
    result.stdout_bytes = consumer.get_stdout_bytes();
    result.stderr_bytes = consumer.get_stderr_bytes();

    auto usage = cgroup.collect_usage();
    result.cpu_time_ms = usage.cpu_time_ms;
    result.memory_peak_bytes = usage.memory_peak_bytes;
    result.pids_peak = usage.pids_peak;
    result.oom_killed = usage.oom_killed;

    // Assess termination reason
    assess_termination(status, timed_out, usage, result);

    // Ensure all descendants are terminated and cgroup cleaned up
    if (cgroup.is_initialized()) {
        cgroup.terminate_all(50);
        cgroup.destroy();
    }

    // Clean up ephemeral sandbox root mount directory
    std::string sb_root = "/tmp/runbox_sb_" + config.execution_id;
    std::error_code ec;
    std::filesystem::remove_all(sb_root, ec);

    return result;
}

std::vector<std::string> Supervisor::prepare_argv(const JobConfig& config) {
    std::vector<std::string> full_argv;
    full_argv.push_back(config.executable_path);
    for (const auto& arg : config.argv) {
        full_argv.push_back(arg);
    }
    return full_argv;
}

bool Supervisor::apply_child_security(const JobConfig& config) {
    security::SecurityLimits sec_limits;
    sec_limits.cpu_seconds = static_cast<uint32_t>((config.limits.timeout_ms + 999) / 1000);
    sec_limits.as_limit_bytes = 0;
    if (config.limits.process_limit > 0) {
        sec_limits.max_pids = config.limits.process_limit;
    } else {
        sec_limits.max_pids = 0;
    }
    security::PrivilegeManager priv_mgr(sec_limits);

    priv_mgr.enable_no_new_privs();
    priv_mgr.apply_rlimits();
    priv_mgr.drop_capabilities();

    seccomp::SeccompProfile sc_profile = seccomp::SeccompProfile::Minimal;
    if (config.language == "python" || config.language == "python3") {
        sc_profile = seccomp::SeccompProfile::PythonExecution;
    } else if (config.language == "cpp_compile") {
        sc_profile = seccomp::SeccompProfile::CppCompilation;
    } else if (config.language == "cpp") {
        sc_profile = seccomp::SeccompProfile::CppExecution;
    }
    seccomp::SeccompFilter sc_filter(sc_profile);
    return sc_filter.install();
}

void Supervisor::setup_child_io(int stdin_read_fd, int stdout_write_fd, int stderr_write_fd) {
    if (stdin_read_fd >= 0) {
        ::dup2(stdin_read_fd, STDIN_FILENO);
    }
    if (stdout_write_fd >= 0) {
        ::dup2(stdout_write_fd, STDOUT_FILENO);
    }
    if (stderr_write_fd >= 0) {
        ::dup2(stderr_write_fd, STDERR_FILENO);
    }
    process::close_fds_except({STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO});
}

void Supervisor::assess_termination(int status, bool timed_out, const cgroups::ResourceUsage& usage, monitoring::ExecutionResult& result) {
    if (timed_out) {
        result.reason = monitoring::TerminationReason::TimedOut;
        result.exit_code = 124;
    } else if (usage.oom_killed) {
        result.reason = monitoring::TerminationReason::MemoryLimitExceeded;
        result.exit_code = 137;
    } else if (usage.pids_max_events > 0) {
        result.reason = monitoring::TerminationReason::ProcessLimitExceeded;
    } else if (WIFEXITED(status)) {
        result.exit_code = WEXITSTATUS(status);
        if (result.exit_code == 0) {
            result.reason = monitoring::TerminationReason::NormalExit;
        } else if (result.exit_code > 128 && result.exit_code <= 128 + 64) {
            int sig = result.exit_code - 128;
            if (sig == SIGSYS) {
                result.reason = monitoring::TerminationReason::SecurityViolation;
            } else {
                result.reason = monitoring::TerminationReason::SignalTerminated;
            }
        } else {
            result.reason = monitoring::TerminationReason::NonZeroExit;
        }
    } else if (WIFSIGNALED(status)) {
        int sig = WTERMSIG(status);
        result.exit_code = 128 + sig;
        if (sig == SIGSYS) {
            result.reason = monitoring::TerminationReason::SecurityViolation;
        } else {
            result.reason = monitoring::TerminationReason::SignalTerminated;
        }
    }
}

void Supervisor::execute_child(const JobConfig& config,
                              int sync_c2p_write,
                              int sync_p2c_read,
                              int stdin_read_fd,
                              int stdout_write_fd,
                              int stderr_write_fd) {
    if (config.executable_path.empty()) {
        ::_exit(101);
    }

    // Ensure child drops setuid privilege to real user before unsharing user namespace
    // so that the caller's real UID owns the user namespace and maps cleanly without overflowuid (65534)
    if (::setegid(::getgid()) != 0) {
        // ignore if not setgid
    }
    if (::seteuid(::getuid()) != 0) {
        // ignore if not setuid
    }

    // 1. Establish Linux Namespaces (Unshare)
    namespaces::NamespaceConfig ns_cfg;
    ns_cfg.hostname = "runbox-" + config.execution_id.substr(0, std::min(size_t{8}, config.execution_id.size()));
    namespaces::NamespaceManager ns_mgr(ns_cfg);

    if (!ns_mgr.unshare_namespaces()) {
#ifdef RUNBOX_ENABLE_COVERAGE
        __gcov_dump();
#endif
        ::_exit(101);
    }

    // Notify parent that namespaces are unshared
    char ready = 1;
    ignore_io_result(::write(sync_c2p_write, &ready, 1));
    ::close(sync_c2p_write);

    // Wait for parent to add this process to Cgroup and write UID/GID mappings
    char go = 0;
    ignore_io_result(::read(sync_p2c_read, &go, 1));
    ::close(sync_p2c_read);

    // Initialize in-namespace credentials to root (UID 0 / GID 0)
    if (::setresgid(0, 0, 0) != 0) {
        // ignore if already 0
    }
    if (::setresuid(0, 0, 0) != 0) {
        // ignore if already 0
    }

    // 2. Setup Private Mounts (now that UID 0 mapping is active)
    ns_mgr.setup_private_mounts();

    // 3. Setup Filesystem Isolation
    filesystem::FilesystemConfig fs_cfg;
    fs_cfg.host_workspace_dir = config.workspace_dir;
    fs_cfg.sandbox_root_dir = "/tmp/runbox_sb_" + config.execution_id;
    fs_cfg.enable_landlock = true;
    filesystem::FilesystemManager fs_mgr(fs_cfg);

    // 4. Prepare argv and envp in memory
    auto full_argv = prepare_argv(config);
    std::vector<const char*> argv_ptrs;
    for (const auto& a : full_argv) {
        argv_ptrs.push_back(a.c_str());
    }
    argv_ptrs.push_back(nullptr);

    security::SecurityLimits sec_limits;
    security::PrivilegeManager priv_mgr(sec_limits);
    auto safe_env = priv_mgr.build_safe_environment();
    std::vector<const char*> env_ptrs;
    for (const auto& e : safe_env) {
        env_ptrs.push_back(e.c_str());
    }
    env_ptrs.push_back(nullptr);

#ifdef RUNBOX_ENABLE_COVERAGE
    __gcov_dump();
#endif

    // 5. Setup sandbox filesystem
    fs_mgr.setup_sandbox_filesystem();

    // 6. Set up I/O Redirection
    setup_child_io(stdin_read_fd, stdout_write_fd, stderr_write_fd);

#ifdef RUNBOX_ENABLE_COVERAGE
    __gcov_dump();
#endif

    // 7. Establish pipe to detect parent death race condition before PR_SET_PDEATHSIG
    int pdeath_pipe[2];
    if (::pipe2(pdeath_pipe, O_CLOEXEC) != 0) {
        pdeath_pipe[0] = -1;
        pdeath_pipe[1] = -1;
    }

    // Fork into the new PID namespace so that the workload becomes PID 1
    pid_t workload_pid = ::fork();
    if (workload_pid < 0) {
        if (pdeath_pipe[0] >= 0) { ::close(pdeath_pipe[0]); ::close(pdeath_pipe[1]); }
        std::cerr << "[runbox::child] fork into PID namespace failed: " << strerror(errno) << "\n";
        ::_exit(126);
    }

    if (workload_pid == 0) {
        if (pdeath_pipe[1] >= 0) {
            ::close(pdeath_pipe[1]);
        }

        // Apply Landlock LSM & Seccomp BPF restrictions directly to untrusted workload
        fs_mgr.apply_landlock_rules();
        apply_child_security(config);

        // --- WORKLOAD (PID 1 in isolated PID namespace) ---
        // Ensure parent-death signal is configured AFTER all privilege/credential changes
        ::prctl(PR_SET_PDEATHSIG, SIGKILL);

        // Guard against race where intermediate parent terminated before PDEATHSIG was registered
        if (pdeath_pipe[0] >= 0) {
            struct pollfd pfd{};
            pfd.fd = pdeath_pipe[0];
            pfd.events = POLLIN;
            int pret = ::poll(&pfd, 1, 0);
            if (pret > 0 && (pfd.revents & POLLHUP)) {
                ::close(pdeath_pipe[0]);
                ::_exit(1);
            }
            ::close(pdeath_pipe[0]);
        }

        ::execve(config.executable_path.c_str(),
                 const_cast<char* const*>(argv_ptrs.data()),
                 const_cast<char* const*>(env_ptrs.data()));

        std::cerr << "[runbox::child] execve failed: path=" << config.executable_path
                  << " errno=" << errno << " (" << strerror(errno) << ")\n";
        ::_exit(127);
    }

    if (pdeath_pipe[0] >= 0) {
        ::close(pdeath_pipe[0]);
    }

    // --- INTERMEDIATE PROCESS: waits for PID 1, forwards exit status ---
    int status = 0;
    while (::waitpid(workload_pid, &status, 0) < 0) {
        if (errno == EINTR) continue;
        break;
    }

    if (pdeath_pipe[1] >= 0) {
        ::close(pdeath_pipe[1]);
    }

    // Flush gcov coverage profile counters before child exits
#ifdef RUNBOX_ENABLE_COVERAGE
    __gcov_dump();
#endif

    if (WIFEXITED(status)) {
        ::_exit(WEXITSTATUS(status));
    } else if (WIFSIGNALED(status)) {
        int sig = WTERMSIG(status);
        ::signal(sig, SIG_DFL);
        ::raise(sig);
        ::_exit(128 + sig);
    }
    ::_exit(1);
}

} // namespace runbox::supervisor
