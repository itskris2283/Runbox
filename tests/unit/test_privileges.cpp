#include <gtest/gtest.h>
#include "core/security/privileges.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/prctl.h>

using namespace runbox::security;

TEST(PrivilegeTest, NoNewPrivsAndRlimits) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SecurityLimits limits;
        limits.cpu_seconds = 2;
        limits.as_limit_bytes = 128ULL * 1024ULL * 1024ULL;
        limits.max_fds = 32;

        PrivilegeManager mgr(limits);
        if (!mgr.enable_no_new_privs()) {
            ::_exit(1);
        }
        if (!mgr.apply_rlimits()) {
            ::_exit(2);
        }
        if (!mgr.drop_capabilities()) {
            ::_exit(3);
        }

        // Verify rlimit was set
        struct rlimit rl{};
        ::getrlimit(RLIMIT_CPU, &rl);
        if (rl.rlim_cur != 2) {
            ::_exit(4);
        }

        exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(PrivilegeTest, SafeEnvironmentConstruction) {
    PrivilegeManager mgr;
    auto env = mgr.build_safe_environment();
    EXPECT_FALSE(env.empty());

    bool has_path = false;
    bool has_tmp = false;
    for (const auto& e : env) {
        if (e.rfind("PATH=", 0) == 0) has_path = true;
        if (e.rfind("TMPDIR=", 0) == 0) has_tmp = true;
        EXPECT_EQ(e.find("AWS_"), std::string::npos);
        EXPECT_EQ(e.find("SECRET"), std::string::npos);
        EXPECT_EQ(e.find("PASSWORD"), std::string::npos);
    }
    EXPECT_TRUE(has_path);
    EXPECT_TRUE(has_tmp);
}

TEST(PrivilegeTest, CoreDumpDisabledByRlimits) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        PrivilegeManager mgr;
        mgr.apply_rlimits();

        struct rlimit rl{};
        ::getrlimit(RLIMIT_CORE, &rl);
        if (rl.rlim_cur != 0 || rl.rlim_max != 0) {
            ::_exit(1);
        }
        exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(PrivilegeTest, DropCapabilitiesBoundingSetClearing) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        PrivilegeManager mgr;
        if (!mgr.drop_capabilities()) {
            ::_exit(1);
        }
        exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(PrivilegeTest, VerifyPrivilegesDroppedValidation) {
    PrivilegeManager mgr;
    // Current process has not dropped privileges to 65534, so verify should return false
    EXPECT_FALSE(mgr.verify_privileges_dropped(65534, 65534));
    EXPECT_FALSE(mgr.verify_privileges_dropped(::getuid(), 9999));
    EXPECT_FALSE(mgr.verify_privileges_dropped(9999, ::getgid()));
    // Current process matches uid/gid, but PR_SET_NO_NEW_PRIVS is 0, so should return false
    EXPECT_FALSE(mgr.verify_privileges_dropped(::getuid(), ::getgid()));
}

TEST(PrivilegeTest, ApplyRlimitsAllBoundsAndDropIdentity) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SecurityLimits limits;
        limits.cpu_seconds = 5;
        limits.as_limit_bytes = 256ULL * 1024ULL * 1024ULL;
        limits.fsize_limit_bytes = 10ULL * 1024ULL * 1024ULL;
        limits.max_pids = 64;
        limits.max_fds = 128;

        PrivilegeManager mgr(limits);
        bool rl_ok = mgr.apply_rlimits();
        bool id_ok = mgr.drop_identity(::getuid(), ::getgid());

        exit((rl_ok && id_ok) ? 0 : 1);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}
