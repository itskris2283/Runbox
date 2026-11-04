#include <gtest/gtest.h>
#include "core/seccomp/seccomp_rules.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <sys/syscall.h>



using namespace runbox::seccomp;

TEST(SeccompTest, FilterBlocksProhibitedSyscall) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter(SeccompProfile::Minimal);
        if (!filter.install()) {
            ::_exit(10);
        }

        long ret = ::syscall(SYS_reboot, 0, 0, 0, 0);
        (void)ret;
        ::_exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFSIGNALED(status));
    EXPECT_EQ(WTERMSIG(status), SIGSYS);
}

TEST(SeccompTest, FilterBlocksMountSyscall) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter(SeccompProfile::Minimal);
        if (!filter.install()) {
            ::_exit(10);
        }

        long ret = ::syscall(SYS_mount, nullptr, nullptr, nullptr, 0, nullptr);
        (void)ret;
        ::_exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFSIGNALED(status));
    EXPECT_EQ(WTERMSIG(status), SIGSYS);
}

TEST(SeccompTest, FilterBlocksBpfSyscall) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter(SeccompProfile::Minimal);
        if (!filter.install()) {
            ::_exit(10);
        }

        long ret = ::syscall(SYS_bpf, 0, nullptr, 0);
        (void)ret;
        ::_exit(0);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFSIGNALED(status));
    EXPECT_EQ(WTERMSIG(status), SIGSYS);
}

TEST(SeccompTest, PythonProfileInstallation) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter(SeccompProfile::PythonExecution);
        bool ok = filter.install();
        exit(ok ? 0 : 1);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(SeccompTest, CppProfilesInstallation) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter1(SeccompProfile::CppCompilation);
        bool ok1 = filter1.install();
        exit(ok1 ? 0 : 1);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(SeccompTest, CppExecutionProfileInstallation) {
    pid_t pid = ::fork();
    ASSERT_GE(pid, 0);

    if (pid == 0) {
        SeccompFilter filter2(SeccompProfile::CppExecution);
        bool ok2 = filter2.install();
        exit(ok2 ? 0 : 1);
    }

    int status = 0;
    ::waitpid(pid, &status, 0);
    EXPECT_TRUE(WIFEXITED(status));
    EXPECT_EQ(WEXITSTATUS(status), 0);
}

TEST(SeccompTest, ProfileGetters) {
    SeccompFilter f_min(SeccompProfile::Minimal);
    EXPECT_EQ(f_min.get_profile(), SeccompProfile::Minimal);

    SeccompFilter f_py(SeccompProfile::PythonExecution);
    EXPECT_EQ(f_py.get_profile(), SeccompProfile::PythonExecution);

    SeccompFilter f_cpp(SeccompProfile::CppExecution);
    EXPECT_EQ(f_cpp.get_profile(), SeccompProfile::CppExecution);
}
