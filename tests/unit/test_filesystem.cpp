#include <gtest/gtest.h>
#include "core/filesystem/filesystem_isolation.hpp"
#include "core/namespaces/namespaces.hpp"
#include <unistd.h>
#include <sys/wait.h>

using namespace runbox::filesystem;

TEST(FilesystemTest, LandlockRulesetApplication) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        FilesystemConfig cfg;
        cfg.enable_landlock = true;
        FilesystemManager mgr(cfg);

        if (!mgr.apply_landlock_rules()) {
            ::_exit(1);
        }
        exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(FilesystemTest, FilesystemConfigGetters) {
    FilesystemConfig cfg;
    cfg.sandbox_root_dir = "/tmp/test_root";
    cfg.host_workspace_dir = "/tmp/test_ws";

    FilesystemManager mgr(cfg);
    EXPECT_EQ(mgr.get_sandbox_root(), "/tmp/test_root");
    EXPECT_EQ(mgr.get_workspace(), "/tmp/test_ws");
}

TEST(FilesystemTest, FilesystemConfigDefaults) {
    FilesystemConfig cfg;
    EXPECT_TRUE(cfg.enable_landlock);
    EXPECT_TRUE(cfg.mount_proc);
    EXPECT_TRUE(cfg.mount_dev);
    EXPECT_TRUE(cfg.mount_tmp);
}

TEST(FilesystemTest, ApplyLandlockDisabledReturnsTrue) {
    FilesystemConfig cfg;
    cfg.enable_landlock = false;
    FilesystemManager mgr(cfg);
    EXPECT_TRUE(mgr.apply_landlock_rules());
}

TEST(FilesystemTest, TeardownSandboxLifecycle) {
    FilesystemConfig cfg;
    cfg.sandbox_root_dir = "/tmp/test_teardown";
    FilesystemManager mgr(cfg);
    EXPECT_TRUE(mgr.teardown_sandbox());
}

TEST(FilesystemTest, SetupMountsAndMinimalDevInIsolatedNamespace) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        runbox::namespaces::NamespaceConfig ns_cfg;
        ns_cfg.enable_user = true;
        ns_cfg.enable_mount = true;
        runbox::namespaces::NamespaceManager ns_mgr(ns_cfg);

        if (!ns_mgr.unshare_namespaces()) {
            ::_exit(1);
        }
        ns_mgr.setup_private_mounts();

        FilesystemConfig fs_cfg;
        fs_cfg.sandbox_root_dir = "/tmp/test_sb_mounts";
        fs_cfg.host_workspace_dir = "/tmp/test_sb_mounts_ws";
        fs_cfg.mount_proc = false;
        fs_cfg.mount_dev = true;
        fs_cfg.mount_tmp = true;

        FilesystemManager fs_mgr(fs_cfg);
        bool dev_ok = fs_mgr.create_minimal_dev();
        bool mounts_ok = fs_mgr.setup_mounts();

        exit((dev_ok && mounts_ok) ? 0 : 2);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(FilesystemTest, SetupMountsEmptyWorkspaceDir) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        runbox::namespaces::NamespaceConfig ns_cfg;
        ns_cfg.enable_user = true;
        ns_cfg.enable_mount = true;
        runbox::namespaces::NamespaceManager ns_mgr(ns_cfg);

        if (!ns_mgr.unshare_namespaces()) {
            ::_exit(1);
        }
        ns_mgr.setup_private_mounts();

        FilesystemConfig fs_cfg;
        fs_cfg.sandbox_root_dir = "/tmp/test_sb_empty_ws";
        fs_cfg.host_workspace_dir = ""; // Empty workspace dir -> mounts tmpfs
        fs_cfg.mount_proc = false;
        fs_cfg.mount_dev = false;
        fs_cfg.mount_tmp = false;

        FilesystemManager fs_mgr(fs_cfg);
        bool mounts_ok = fs_mgr.setup_mounts();

        exit(mounts_ok ? 0 : 2);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    ASSERT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}
