#include <gtest/gtest.h>
#include <sys/prctl.h>
#include "core/supervisor/supervisor.hpp"
#include "core/supervisor/config.hpp"
#include "core/security/privileges.hpp"

#ifdef RUNBOX_ENABLE_COVERAGE
extern "C" void __gcov_dump(void);
#endif

using namespace runbox::supervisor;
using namespace runbox::monitoring;

TEST(SupervisorIntegrationTest, ExecuteEchoNormalExit) {
    JobConfig cfg;
    cfg.execution_id = "test-echo-normal";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/echo";
    cfg.argv = {"Runbox Sandbox Active"};
    cfg.limits.timeout_ms = 5000;
    cfg.limits.memory_mb = 64;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.reason, TerminationReason::NormalExit);
    EXPECT_NE(res.stdout_output.find("Runbox Sandbox Active"), std::string::npos);
    EXPECT_GT(res.wall_time_ms, 0);
}

TEST(SupervisorIntegrationTest, TimeoutEnforcement) {
    JobConfig cfg;
    cfg.execution_id = "test-timeout-sleep";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sleep";
    cfg.argv = {"10"};
    cfg.limits.timeout_ms = 500; // 500ms limit for 10s sleep

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.reason, TerminationReason::TimedOut);
    EXPECT_LT(res.wall_time_ms, 2000); // Must be enforced well under 2s
}

TEST(SupervisorIntegrationTest, ExecuteNonZeroExit) {
    JobConfig cfg;
    cfg.execution_id = "test-nonzero-exit";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sh";
    cfg.argv = {"-c", "exit 42"};
    cfg.limits.timeout_ms = 3000;
    cfg.limits.memory_mb = 64;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 42);
    EXPECT_EQ(res.reason, TerminationReason::NonZeroExit);
}

TEST(SupervisorIntegrationTest, ExecuteStdinPipeData) {
    JobConfig cfg;
    cfg.execution_id = "test-stdin-pipe";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/cat";
    cfg.stdin_data = "FEEDING_STDIN_PAYLOAD\n";
    cfg.limits.timeout_ms = 3000;
    cfg.limits.memory_mb = 64;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.reason, TerminationReason::NormalExit);
    EXPECT_NE(res.stdout_output.find("FEEDING_STDIN_PAYLOAD"), std::string::npos);
}

TEST(SupervisorIntegrationTest, OutputLimitTruncationEnforced) {
    JobConfig cfg;
    cfg.execution_id = "test-truncation";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sh";
    cfg.argv = {"-c", "head -c 200000 /dev/zero | tr '\\0' 'A'"};
    cfg.limits.timeout_ms = 4000;
    cfg.limits.memory_mb = 64;
    cfg.limits.output_limit_bytes = 4096; // 4 KB limit

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_LE(res.stdout_output.size(), 4096);
    EXPECT_TRUE(res.stdout_truncated);
}

TEST(SupervisorIntegrationTest, ExecutePythonLanguageProfile) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-python";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c", "print('PYTHON_SUPERVISOR_OK')"};
    cfg.limits.timeout_ms = 4000;
    cfg.limits.memory_mb = 128;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.reason, TerminationReason::NormalExit);
    EXPECT_NE(res.stdout_output.find("PYTHON_SUPERVISOR_OK"), std::string::npos);
}

TEST(SupervisorIntegrationTest, ExecuteCppProfilesAndInvalidPath) {
    // 1. Cpp compilation profile
    JobConfig cfg1;
    cfg1.execution_id = "test-sup-cpp-comp";
    cfg1.language = "cpp_compile";
    cfg1.executable_path = "/bin/true";
    cfg1.limits.timeout_ms = 3000;

    Supervisor sup;
    auto res1 = sup.execute_job(cfg1);
    EXPECT_EQ(res1.exit_code, 0);

    // 2. Cpp execution profile
    JobConfig cfg2;
    cfg2.execution_id = "test-sup-cpp-exec";
    cfg2.language = "cpp";
    cfg2.executable_path = "/bin/true";
    cfg2.limits.timeout_ms = 3000;

    auto res2 = sup.execute_job(cfg2);
    EXPECT_EQ(res2.exit_code, 0);

    // 3. Execve failure handling
    JobConfig cfg3;
    cfg3.execution_id = "test-sup-bad-path";
    cfg3.language = "minimal";
    cfg3.executable_path = "/bin/nonexistent_tool_12345";
    cfg3.limits.timeout_ms = 3000;

    auto res3 = sup.execute_job(cfg3);
    EXPECT_NE(res3.exit_code, 0);
}

TEST(SupervisorIntegrationTest, SupervisorSignalTerminationHandling) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-sigterm";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"};
    cfg.limits.timeout_ms = 3000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_NE(res.exit_code, 0);
}

TEST(SupervisorIntegrationTest, SupervisorSecurityViolationSyscallHandling) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-sigsys";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c", "import ctypes; ctypes.CDLL(None).syscall(169, 0, 0, 0, 0)"};
    cfg.limits.timeout_ms = 3000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_NE(res.exit_code, 0);
}

TEST(SupervisorIntegrationTest, StderrTruncationEnforced) {
    JobConfig cfg;
    cfg.execution_id = "test-stderr-trunc";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sh";
    cfg.argv = {"-c", "head -c 200000 /dev/zero | tr '\\0' 'E' >&2"};
    cfg.limits.timeout_ms = 4000;
    cfg.limits.output_limit_bytes = 4096;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_LE(res.stderr_output.size(), 4096);
    EXPECT_TRUE(res.stderr_truncated);
}

TEST(SupervisorIntegrationTest, SupervisorSignalCrashFPEAndSEGV) {
    // SIGSEGV
    JobConfig cfg_segv;
    cfg_segv.execution_id = "test-sup-segv";
    cfg_segv.language = "python";
    cfg_segv.executable_path = "/usr/bin/python3";
    cfg_segv.argv = {"-c", "import ctypes; ctypes.string_at(0)"};
    cfg_segv.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res_segv = sup.execute_job(cfg_segv);
    EXPECT_NE(res_segv.exit_code, 0);
    EXPECT_EQ(res_segv.reason, TerminationReason::SignalTerminated);

    // SIGFPE / Signal Handling
    JobConfig cfg_fpe;
    cfg_fpe.execution_id = "test-sup-fpe";
    cfg_fpe.language = "python";
    cfg_fpe.executable_path = "/usr/bin/python3";
    cfg_fpe.argv = {"-c", "import os, signal; os.kill(os.getpid(), signal.SIGFPE)"};
    cfg_fpe.limits.timeout_ms = 4000;

    auto res_fpe = sup.execute_job(cfg_fpe);
    EXPECT_NE(res_fpe.exit_code, 0);
    EXPECT_TRUE(res_fpe.reason == TerminationReason::SignalTerminated ||
                res_fpe.reason == TerminationReason::NonZeroExit);
}

TEST(SupervisorIntegrationTest, SupervisorProcessLimitForkBombMitigation) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-pids";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sh";
    cfg.argv = {"-c", ":(){ :|:& };:"};
    cfg.limits.timeout_ms = 2000;
    cfg.limits.process_limit = 5;

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_TRUE(res.reason == TerminationReason::ProcessLimitExceeded ||
                res.reason == TerminationReason::TimedOut ||
                res.reason == TerminationReason::NonZeroExit ||
                res.reason == TerminationReason::SignalTerminated);
}

TEST(SupervisorIntegrationTest, SupervisorMemoryLimitExceededOOM) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-oom";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c", "x = 'A' * (64 * 1024 * 1024)"};
    cfg.limits.timeout_ms = 4000;
    cfg.limits.memory_mb = 16;

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_TRUE(res.oom_killed || res.reason == TerminationReason::MemoryLimitExceeded || res.exit_code != 0);
}

TEST(SupervisorIntegrationTest, SupervisorDoubleForkDescendantCleanup) {
    JobConfig cfg;
    cfg.execution_id = "test-sup-doublefork";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sh";
    cfg.argv = {"-c", "nohup sleep 60 >/dev/null 2>&1 & exit 0"};
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.reason, TerminationReason::NormalExit);
}

TEST(SupervisorIntegrationTest, PrepareArgvVariousProfiles) {
    JobConfig cfg;
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c", "print('hello')", "arg2"};

    auto full_argv = Supervisor::prepare_argv(cfg);
    ASSERT_EQ(full_argv.size(), 4);
    EXPECT_EQ(full_argv[0], "/usr/bin/python3");
    EXPECT_EQ(full_argv[1], "-c");
    EXPECT_EQ(full_argv[2], "print('hello')");
    EXPECT_EQ(full_argv[3], "arg2");

    JobConfig cfg_empty;
    cfg_empty.executable_path = "/bin/true";
    auto full_argv_empty = Supervisor::prepare_argv(cfg_empty);
    ASSERT_EQ(full_argv_empty.size(), 1);
    EXPECT_EQ(full_argv_empty[0], "/bin/true");
}

TEST(SupervisorIntegrationTest, SetupChildIoRedirection) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        int pipe_in[2];
        int pipe_out[2];
        int pipe_err[2];
        if (::pipe(pipe_in) != 0 || ::pipe(pipe_out) != 0 || ::pipe(pipe_err) != 0) {
            ::_exit(1);
        }

        Supervisor::setup_child_io(pipe_in[0], pipe_out[1], pipe_err[1]);

        ::close(pipe_in[1]);
        ::close(pipe_out[0]);
        ::close(pipe_err[0]);
#ifdef RUNBOX_ENABLE_COVERAGE
        __gcov_dump();
#endif
        ::_exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}

TEST(SupervisorIntegrationTest, ApplyChildSecurityVariousProfiles) {
    const std::vector<std::string> languages = {"python", "cpp_compile", "cpp", "minimal"};

    for (const auto& lang : languages) {
        pid_t pid = ::fork();
        ASSERT_GE(pid, 0);

        if (pid == 0) {
            JobConfig cfg;
            cfg.language = lang;
            cfg.limits.timeout_ms = 5000;
            bool ok = Supervisor::apply_child_security(cfg);
#ifdef RUNBOX_ENABLE_COVERAGE
            __gcov_dump();
#endif
            ::_exit(ok ? 0 : 1);
        }

        int status = 0;
        ::waitpid(pid, &status, 0);
        EXPECT_TRUE(WIFEXITED(status) && WEXITSTATUS(status) == 0) << "Failed profile: " << lang;
    }
}

TEST(SupervisorIntegrationTest, AssessTerminationComprehensiveBranches) {
    runbox::cgroups::ResourceUsage usage{};
    runbox::monitoring::ExecutionResult res{};

    // 1. Timed out
    Supervisor::assess_termination(0, true, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::TimedOut);
    EXPECT_EQ(res.exit_code, 124);

    // 2. OOM Killed via Cgroup
    usage.oom_killed = true;
    Supervisor::assess_termination(0, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::MemoryLimitExceeded);
    EXPECT_EQ(res.exit_code, 137);
    usage.oom_killed = false;

    // 3. Process Limit Exceeded via Cgroup pids.events
    usage.pids_max_events = 5;
    Supervisor::assess_termination(0, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::ProcessLimitExceeded);
    usage.pids_max_events = 0;

    // 4. WIFEXITED branches:
    // 4a. Normal exit (exit code 0)
    int st_exit_0 = 0 << 8;
    Supervisor::assess_termination(st_exit_0, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::NormalExit);
    EXPECT_EQ(res.exit_code, 0);

    // 4b. Exit with 128 + SIGSYS
    int st_exit_sigsys = (128 + SIGSYS) << 8;
    Supervisor::assess_termination(st_exit_sigsys, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::SecurityViolation);
    EXPECT_EQ(res.exit_code, 128 + SIGSYS);

    // 4c. Exit with 128 + SIGTERM
    int st_exit_sigterm = (128 + SIGTERM) << 8;
    Supervisor::assess_termination(st_exit_sigterm, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::SignalTerminated);
    EXPECT_EQ(res.exit_code, 128 + SIGTERM);

    // 4d. Normal non-zero exit (e.g. exit code 42)
    int st_exit_42 = 42 << 8;
    Supervisor::assess_termination(st_exit_42, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::NonZeroExit);
    EXPECT_EQ(res.exit_code, 42);

    // 5. WIFSIGNALED branches:
    // 5a. Terminated by SIGSYS
    int st_sig_sys = SIGSYS & 0x7f;
    Supervisor::assess_termination(st_sig_sys, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::SecurityViolation);
    EXPECT_EQ(res.exit_code, 128 + SIGSYS);

    // 5b. Terminated by SIGKILL
    int st_sig_kill = SIGKILL & 0x7f;
    Supervisor::assess_termination(st_sig_kill, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::SignalTerminated);
    EXPECT_EQ(res.exit_code, 128 + SIGKILL);

    // 5c. Terminated by SIGSEGV
    int st_sig_segv = SIGSEGV & 0x7f;
    Supervisor::assess_termination(st_sig_segv, false, usage, res);
    EXPECT_EQ(res.reason, TerminationReason::SignalTerminated);
    EXPECT_EQ(res.exit_code, 128 + SIGSEGV);
}

TEST(SupervisorIntegrationTest, ExecuteJobFallbackWhenCgroupInitFails) {
    JobConfig cfg;
    cfg.execution_id = "test-cgroup-fail-fallback";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/echo";
    cfg.argv = {"fallback-mode"};
    cfg.limits.timeout_ms = 4000;
    cfg.limits.memory_mb = 64;

    Supervisor sup;
    // Pass an invalid base cgroup path so initialize() fails and proceeds with rlimits
    auto res = sup.execute_job(cfg, "/proc/sys/fs/cgroup/nonexistent_sub_404");
    EXPECT_EQ(res.exit_code, 0);
    EXPECT_NE(res.stdout_output.find("fallback-mode"), std::string::npos);
}

TEST(SupervisorIntegrationTest, TimerfdMonotonicPrecision) {
    JobConfig cfg;
    cfg.execution_id = "test-timerfd-mono";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/sleep";
    cfg.argv = {"10"};
    cfg.limits.timeout_ms = 300; // 300ms limit

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.reason, TerminationReason::TimedOut);
    EXPECT_GE(res.wall_time_ms, 300);
    EXPECT_LE(res.wall_time_ms, 550); // subsecond precision enforced by timerfd
}

TEST(SupervisorIntegrationTest, ExecuteChildDirectInvocation) {
    JobConfig cfg;
    cfg.execution_id = "test-exec-child-direct";
    cfg.language = "minimal";
    cfg.executable_path = "/bin/true";
    cfg.limits.timeout_ms = 2000;

    int c2p[2];
    int p2c[2];
    ASSERT_EQ(::pipe(c2p), 0);
    ASSERT_EQ(::pipe(p2c), 0);

    pid_t pid = ::fork();
    if (pid == 0) {
        ::close(c2p[0]);
        ::close(p2c[1]);
        Supervisor sup;
        sup.execute_child(cfg, c2p[1], p2c[0], -1, -1, -1);
        ::_exit(0);
    }

    ::close(c2p[1]);
    ::close(p2c[0]);

    // Read ready from child
    char ready = 0;
    ASSERT_EQ(::read(c2p[0], &ready, 1), 1);
    EXPECT_EQ(ready, 1);

    // Send go to child
    char go = 1;
    ASSERT_EQ(::write(p2c[1], &go, 1), 1);

    ::close(c2p[0]);
    ::close(p2c[1]);

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(SupervisorIntegrationTest, ExecuteJobFailsGracefullyOnEmptyExecutablePath) {
    JobConfig cfg;
    cfg.execution_id = "test-empty-exec";
    cfg.executable_path = ""; // Empty executable path causes early child exit

    Supervisor sup;
    auto res = sup.execute_job(cfg);
    EXPECT_EQ(res.reason, TerminationReason::InternalError);
    EXPECT_NE(res.error_message.find("Child failed during initial sandbox setup"), std::string::npos);
}

TEST(SupervisorIntegrationTest, ParentDeathSignalImmediateTeardownOnSupervisorCrash) {
    // Make current process a subreaper so orphaned grandchildren are reparented here
    ::prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0);

    int pipe_sync[2];
    int pid_pipe[2];
    ASSERT_EQ(::pipe(pipe_sync), 0);
    ASSERT_EQ(::pipe(pid_pipe), 0);

    pid_t supervisor_pid = ::fork();
    if (supervisor_pid == 0) {
        ::close(pipe_sync[0]);
        ::close(pid_pipe[0]);
        pid_t parent_pid = ::getpid();

        pid_t child_pid = ::fork();
        if (child_pid == 0) {
            ::close(pid_pipe[1]);
            ::prctl(PR_SET_PDEATHSIG, SIGKILL);
            if (::getppid() != parent_pid) {
                ::_exit(1);
            }
            char r = 1;
            ssize_t w = ::write(pipe_sync[1], &r, 1);
            (void)w;
            ::close(pipe_sync[1]);

            // Child waits indefinitely; supervisor death should kill it with SIGKILL
            while (true) {
                ::pause();
            }
            ::_exit(0);
        }

        // Send child_pid to test runner
        ssize_t w_pid = ::write(pid_pipe[1], &child_pid, sizeof(child_pid));
        (void)w_pid;
        ::close(pid_pipe[1]);
        ::close(pipe_sync[1]);

        // Supervisor terminates abruptly
        ::usleep(20000);
        ::_exit(0);
    }

    ::close(pipe_sync[1]);
    ::close(pid_pipe[1]);

    pid_t grandchild_pid = 0;
    ssize_t r_pid = ::read(pid_pipe[0], &grandchild_pid, sizeof(grandchild_pid));
    EXPECT_EQ(r_pid, static_cast<ssize_t>(sizeof(grandchild_pid)));
    ::close(pid_pipe[0]);

    char ready = 0;
    ssize_t r_ready = ::read(pipe_sync[0], &ready, 1);
    EXPECT_EQ(r_ready, 1);
    ::close(pipe_sync[0]);

    // Wait for supervisor to exit
    int status = 0;
    ::waitpid(supervisor_pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);

    // Because we are subreaper, grandchild is reparented to us and killed by PDEATHSIG
    int grandchild_status = 0;
    pid_t waited = ::waitpid(grandchild_pid, &grandchild_status, 0);
    EXPECT_EQ(waited, grandchild_pid);
    EXPECT_TRUE(WIFSIGNALED(grandchild_status));
    EXPECT_EQ(WTERMSIG(grandchild_status), SIGKILL);

    ::prctl(PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0);
}

TEST(SupervisorIntegrationTest, ParentDeathSignalRaceDetection) {
    int sync_pipe[2];
    int result_pipe[2];
    ASSERT_EQ(::pipe(sync_pipe), 0);
    ASSERT_EQ(::pipe(result_pipe), 0);

    pid_t intermediate_parent = ::fork();
    if (intermediate_parent == 0) {
        ::close(result_pipe[0]);
        pid_t parent_pid = ::getpid();

        pid_t child = ::fork();
        if (child == 0) {
            ::close(sync_pipe[1]);
            // Wait until intermediate_parent has terminated
            char token = 0;
            ssize_t r_tok = ::read(sync_pipe[0], &token, 1);
            (void)r_tok;
            ::close(sync_pipe[0]);

            ::prctl(PR_SET_PDEATHSIG, SIGKILL);
            int exit_code = 0;
            // Intermediate parent has died; getppid() will not match parent_pid
            if (::getppid() != parent_pid) {
                exit_code = 42;
            }
            ssize_t w = ::write(result_pipe[1], &exit_code, sizeof(exit_code));
            (void)w;
            ::close(result_pipe[1]);
            ::_exit(0);
        }

        ::close(sync_pipe[0]);
        ::close(sync_pipe[1]);
        ::close(result_pipe[1]);
        ::_exit(0);
    }

    ::close(sync_pipe[0]);
    ::close(result_pipe[1]);

    // Ensure intermediate parent has fully terminated
    int s = 0;
    ::waitpid(intermediate_parent, &s, 0);

    // Unblock child now that its parent is confirmed dead
    char tok = 1;
    ssize_t w_tok = ::write(sync_pipe[1], &tok, 1);
    (void)w_tok;
    ::close(sync_pipe[1]);

    int child_exit_code = 0;
    ssize_t r_res = ::read(result_pipe[0], &child_exit_code, sizeof(child_exit_code));
    EXPECT_EQ(r_res, static_cast<ssize_t>(sizeof(child_exit_code)));
    ::close(result_pipe[0]);

    EXPECT_EQ(child_exit_code, 42);
}

TEST(SupervisorIntegrationTest, ParentDeathSignalPreservedAcrossCapabilitiesDrop) {
    int sig = 0;
    ::prctl(PR_SET_PDEATHSIG, SIGKILL);
    ::prctl(PR_GET_PDEATHSIG, &sig);
    EXPECT_EQ(sig, SIGKILL);

    runbox::security::SecurityLimits sec_limits;
    runbox::security::PrivilegeManager priv_mgr(sec_limits);
    priv_mgr.drop_capabilities();

    int sig_after = 0;
    ::prctl(PR_GET_PDEATHSIG, &sig_after);
    EXPECT_EQ(sig_after, SIGKILL);

    ::prctl(PR_SET_PDEATHSIG, 0);
}
