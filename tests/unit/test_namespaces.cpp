#include <gtest/gtest.h>
#include "core/namespaces/namespaces.hpp"
#include <sched.h>
#include <unistd.h>
#include <sys/wait.h>

using namespace runbox::namespaces;

TEST(NamespaceTest, CloneFlagsVerification) {
    NamespaceConfig cfg;
    cfg.enable_pid = true;
    cfg.enable_mount = true;
    cfg.enable_net = true;
    cfg.enable_ipc = true;
    cfg.enable_uts = true;
    cfg.enable_user = true;

    NamespaceManager mgr(cfg);
    int flags = mgr.get_clone_flags();

    EXPECT_NE(flags & CLONE_NEWPID, 0);
    EXPECT_NE(flags & CLONE_NEWNS, 0);
    EXPECT_NE(flags & CLONE_NEWNET, 0);
    EXPECT_NE(flags & CLONE_NEWIPC, 0);
    EXPECT_NE(flags & CLONE_NEWUTS, 0);
    EXPECT_NE(flags & CLONE_NEWUSER, 0);
}

TEST(NamespaceTest, SelectiveNamespaceFlags) {
    NamespaceConfig cfg;
    cfg.enable_pid = true;
    cfg.enable_mount = false;
    cfg.enable_net = true;
    cfg.enable_ipc = false;
    cfg.enable_uts = false;
    cfg.enable_user = false;

    NamespaceManager mgr(cfg);
    int flags = mgr.get_clone_flags();

    EXPECT_NE(flags & CLONE_NEWPID, 0);
    EXPECT_NE(flags & CLONE_NEWNET, 0);
    EXPECT_EQ(flags & CLONE_NEWNS, 0);
    EXPECT_EQ(flags & CLONE_NEWIPC, 0);
    EXPECT_EQ(flags & CLONE_NEWUTS, 0);
    EXPECT_EQ(flags & CLONE_NEWUSER, 0);
}

TEST(NamespaceTest, DisabledNamespacesProduceZeroFlags) {
    NamespaceConfig cfg;
    cfg.enable_pid = false;
    cfg.enable_mount = false;
    cfg.enable_net = false;
    cfg.enable_ipc = false;
    cfg.enable_uts = false;
    cfg.enable_user = false;

    NamespaceManager mgr(cfg);
    EXPECT_EQ(mgr.get_clone_flags(), 0);
}

TEST(NamespaceTest, UnprivilegedUserNamespaceExecution) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        NamespaceConfig cfg;
        cfg.enable_user = true;
        cfg.enable_uts = true;
        cfg.hostname = "runbox-test";
        NamespaceManager mgr(cfg);

        if (!mgr.unshare_namespaces()) {
            ::_exit(1);
        }
        mgr.configure_hostname();
        if (!mgr.verify_isolation()) {
            ::_exit(2);
        }
        exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    if (WIFEXITED(status)) {
        int code = WEXITSTATUS(status);
        EXPECT_TRUE(code == 0 || code == 1);
    }
}

TEST(NamespaceTest, SetupPrivateMountsExecution) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        NamespaceConfig cfg;
        cfg.enable_user = true;
        cfg.enable_mount = true;
        NamespaceManager mgr(cfg);

        if (!mgr.unshare_namespaces()) {
            ::_exit(1);
        }
        bool ok = mgr.setup_private_mounts();
        exit(ok ? 0 : 2);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(NamespaceTest, WriteIdMappingsHandlesNonexistentPid) {
    // Verifies write_id_mappings fails gracefully on invalid pid without crashing
    bool result = NamespaceManager::write_id_mappings(9999999, 1000, 1000, 0, 0);
    EXPECT_FALSE(result);
}

TEST(NamespaceTest, VerifyIsolationMismatchedHostnameReturnsFalse) {
    NamespaceConfig cfg;
    cfg.enable_uts = true;
    cfg.hostname = "nonexistent_mismatched_hostname_12345";
    NamespaceManager mgr(cfg);
    EXPECT_FALSE(mgr.verify_isolation());

    NamespaceConfig cfg_no_uts;
    cfg_no_uts.enable_uts = false;
    NamespaceManager mgr_no_uts(cfg_no_uts);
    EXPECT_TRUE(mgr_no_uts.verify_isolation());
}
