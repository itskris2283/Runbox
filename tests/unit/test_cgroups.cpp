#include <gtest/gtest.h>
#include "core/cgroups/cgroup_manager.hpp"
#include <unistd.h>
#include <fstream>

using namespace runbox::cgroups;

TEST(CgroupTest, InitializeAndDestroyLifecycle) {
    std::string test_id = "test-cg-unit-" + std::to_string(::getpid());
    ResourceLimits limits;
    limits.memory_max_bytes = 64ULL * 1024ULL * 1024ULL; // 64 MB
    limits.cpu_quota_percent = 25;
    limits.pids_max = 10;

    CgroupManager mgr(test_id, "/sys/fs/cgroup/runbox", limits);
    bool init_ok = mgr.initialize();
    if (init_ok) {
        EXPECT_TRUE(mgr.is_initialized());
        auto usage = mgr.collect_usage();
        EXPECT_EQ(usage.oom_killed, false);

        EXPECT_TRUE(mgr.terminate_all(50));
        EXPECT_TRUE(mgr.destroy());
        EXPECT_FALSE(mgr.is_initialized());
    } else {
        EXPECT_FALSE(mgr.is_initialized());
    }
}

TEST(CgroupTest, TerminateAllWhenUninitializedReturnsTrue) {
    CgroupManager mgr("uninit-term", "/sys/fs/cgroup/runbox");
    EXPECT_TRUE(mgr.terminate_all(100));
}

TEST(CgroupTest, ResourceLimitsDefaults) {
    ResourceLimits limits;
    EXPECT_EQ(limits.memory_max_bytes, 128ULL * 1024ULL * 1024ULL);
    EXPECT_EQ(limits.memory_swap_max_bytes, 0);
    EXPECT_EQ(limits.cpu_quota_percent, 50);
    EXPECT_EQ(limits.pids_max, 32);
    EXPECT_TRUE(limits.enable_oom_group);
}

TEST(CgroupTest, AddProcessFailsWhenUninitialized) {
    CgroupManager mgr("uninit-job", "/sys/fs/cgroup/runbox");
    EXPECT_FALSE(mgr.is_initialized());
    EXPECT_FALSE(mgr.add_process(::getpid()));
}

TEST(CgroupTest, CollectUsageWhenUninitializedReturnsZeros) {
    CgroupManager mgr("uninit-job", "/sys/fs/cgroup/runbox");
    auto usage = mgr.collect_usage();
    EXPECT_EQ(usage.cpu_time_ms, 0);
    EXPECT_EQ(usage.memory_peak_bytes, 0);
    EXPECT_EQ(usage.pids_peak, 0);
    EXPECT_FALSE(usage.oom_killed);
}

TEST(CgroupTest, MoveConstructorTransfersOwnership) {
    ResourceLimits limits;
    limits.memory_max_bytes = 32ULL * 1024ULL * 1024ULL;
    CgroupManager mgr1("move-job-1", "/sys/fs/cgroup/runbox", limits);

    bool init_ok = mgr1.initialize();
    if (init_ok) {
        EXPECT_TRUE(mgr1.is_initialized());
        CgroupManager mgr2(std::move(mgr1));
        EXPECT_FALSE(mgr1.is_initialized());
        EXPECT_TRUE(mgr2.is_initialized());
        mgr2.destroy();
    }
}

TEST(CgroupTest, MoveAssignmentTransfersOwnership) {
    ResourceLimits limits;
    limits.memory_max_bytes = 32ULL * 1024ULL * 1024ULL;
    CgroupManager mgr1("move-job-2", "/sys/fs/cgroup/runbox", limits);
    CgroupManager mgr2("move-job-dest", "/sys/fs/cgroup/runbox", limits);

    bool init_ok = mgr1.initialize();
    if (init_ok) {
        mgr2 = std::move(mgr1);
        EXPECT_FALSE(mgr1.is_initialized());
        EXPECT_TRUE(mgr2.is_initialized());
        mgr2.destroy();
    }
}

TEST(CgroupTest, MockCgroupComprehensiveUsageParsing) {
    std::string base = "/tmp/test_cgroup_mock_base_" + std::to_string(::getpid());
    std::string exec_id = "job_stats";
    std::string cgroup_dir = base + "/" + exec_id;

    ResourceLimits limits;
    limits.memory_max_bytes = 64ULL * 1024ULL * 1024ULL;
    limits.cpu_quota_percent = 50;
    limits.pids_max = 20;
    limits.enable_oom_group = true;

    CgroupManager mgr(exec_id, base, limits);
    EXPECT_TRUE(mgr.initialize());
    EXPECT_TRUE(mgr.is_initialized());

    // Populate mock telemetry files in the cgroup directory
    {
        std::ofstream f(cgroup_dir + "/memory.peak");
        f << "20971520\n";
    }
    {
        std::ofstream f(cgroup_dir + "/memory.current");
        f << "10485760\n";
    }
    {
        std::ofstream f(cgroup_dir + "/memory.events");
        f << "oom 2\noom_kill 1\n";
    }
    {
        std::ofstream f(cgroup_dir + "/cpu.stat");
        f << "usage_usec 150000\nnr_throttled 5\n";
    }
    {
        std::ofstream f(cgroup_dir + "/pids.current");
        f << "3\n";
    }
    {
        std::ofstream f(cgroup_dir + "/pids.peak");
        f << "7\n";
    }
    {
        std::ofstream f(cgroup_dir + "/pids.events");
        f << "max 4\n";
    }

    auto usage = mgr.collect_usage();
    EXPECT_EQ(usage.memory_peak_bytes, 20971520ULL);
    EXPECT_EQ(usage.memory_current_bytes, 10485760ULL);
    EXPECT_EQ(usage.oom_count, 2U);
    EXPECT_EQ(usage.oom_kill_count, 1U);
    EXPECT_TRUE(usage.oom_killed);
    EXPECT_EQ(usage.cpu_time_ms, 150ULL);
    EXPECT_EQ(usage.nr_throttled, 5ULL);
    EXPECT_EQ(usage.pids_current, 3U);
    EXPECT_EQ(usage.pids_peak, 7U);
    EXPECT_EQ(usage.pids_max_events, 4U);

    // Test terminate_all timeout loop with mock PID
    {
        std::ofstream f(cgroup_dir + "/cgroup.procs");
        f << "99999999\n";
    }
    EXPECT_TRUE(mgr.terminate_all(20));

    // Clean up regular files inside mock cgroup directory so rmdir succeeds
    std::vector<std::string> mock_files = {
        "memory.max", "memory.swap.max", "memory.oom.group", "cpu.max", "pids.max",
        "memory.peak", "memory.current", "memory.events", "cpu.stat",
        "pids.current", "pids.peak", "pids.events", "cgroup.procs", "cgroup.kill"
    };
    for (const auto& file : mock_files) {
        ::unlink((cgroup_dir + "/" + file).c_str());
    }

    EXPECT_TRUE(mgr.destroy());
    ::unlink((base + "/cgroup.subtree_control").c_str());
    ::rmdir(base.c_str());
}

TEST(CgroupTest, InitializeFailsGracefullyOnInvalidPath) {
    ResourceLimits limits;
    limits.memory_max_bytes = 16ULL * 1024ULL * 1024ULL;
    CgroupManager mgr("invalid_exec", "/proc/sys/fs/cgroup/invalid_impossible_path", limits);
    EXPECT_FALSE(mgr.initialize());
    EXPECT_FALSE(mgr.is_initialized());
}

