#include <gtest/gtest.h>
#include "core/process/process.hpp"
#include <fcntl.h>
#include <unistd.h>
#include <vector>

using namespace runbox::process;

TEST(ProcessTest, ScopedFdDefaultInvalid) {
    ScopedFd fd;
    EXPECT_FALSE(fd.valid());
    EXPECT_EQ(fd.get(), -1);
}

TEST(ProcessTest, ScopedFdOpenAndClose) {
    int raw_fd = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    ASSERT_GE(raw_fd, 0);

    {
        ScopedFd scoped(raw_fd);
        EXPECT_TRUE(scoped.valid());
        EXPECT_EQ(scoped.get(), raw_fd);
    }

    // ScopedFd destructor should have closed the raw_fd
    // A second close should return -1 with EBADF
    EXPECT_EQ(::close(raw_fd), -1);
    EXPECT_EQ(errno, EBADF);
}

TEST(ProcessTest, ScopedFdMoveConstructorAndAssignment) {
    int raw_fd = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    ASSERT_GE(raw_fd, 0);

    ScopedFd fd1(raw_fd);
    ScopedFd fd2(std::move(fd1));
    EXPECT_FALSE(fd1.valid());
    EXPECT_TRUE(fd2.valid());
    EXPECT_EQ(fd2.get(), raw_fd);

    ScopedFd fd3;
    fd3 = std::move(fd2);
    EXPECT_FALSE(fd2.valid());
    EXPECT_TRUE(fd3.valid());
    EXPECT_EQ(fd3.get(), raw_fd);
}

TEST(ProcessTest, ScopedFdRelease) {
    int raw_fd = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    ASSERT_GE(raw_fd, 0);

    ScopedFd scoped(raw_fd);
    int released_fd = scoped.release();
    EXPECT_EQ(released_fd, raw_fd);
    EXPECT_FALSE(scoped.valid());

    // Clean up manually since ownership was released
    ::close(released_fd);
}

TEST(ProcessTest, ScopedFdReset) {
    int fd1 = ::open("/dev/null", O_RDONLY | O_CLOEXEC);
    int fd2 = ::open("/dev/zero", O_RDONLY | O_CLOEXEC);
    ASSERT_GE(fd1, 0);
    ASSERT_GE(fd2, 0);

    ScopedFd scoped(fd1);
    scoped.reset(fd2);
    EXPECT_EQ(scoped.get(), fd2);

    // fd1 must be closed
    EXPECT_EQ(::close(fd1), -1);
    EXPECT_EQ(errno, EBADF);
}

TEST(ProcessTest, ScopedPipeCreationAndCommunication) {
    ScopedPipe p;
    EXPECT_GE(p.read_fd(), 0);
    EXPECT_GE(p.write_fd(), 0);

    const char msg[] = "RUNBOX_PIPE_TEST";
    ssize_t written = ::write(p.write_fd(), msg, sizeof(msg));
    EXPECT_EQ(written, static_cast<ssize_t>(sizeof(msg)));

    char buf[32] = {0};
    ssize_t read_bytes = ::read(p.read_fd(), buf, sizeof(buf));
    EXPECT_EQ(read_bytes, static_cast<ssize_t>(sizeof(msg)));
    EXPECT_STREQ(buf, msg);

    p.close_write();
    EXPECT_EQ(p.write_fd(), -1);
    p.close_read();
    EXPECT_EQ(p.read_fd(), -1);
}

TEST(ProcessTest, ReadStreamBoundedNormalAndTruncated) {
    ScopedPipe p;
    ASSERT_GE(p.read_fd(), 0);
    ASSERT_GE(p.write_fd(), 0);

    // Write 20 bytes
    std::string test_data = "0123456789abcdefghij";
    ASSERT_EQ(::write(p.write_fd(), test_data.data(), test_data.size()), static_cast<ssize_t>(test_data.size()));
    p.close_write();

    // Read bounded to 10 bytes -> should truncate
    std::string buf;
    bool truncated = false;
    bool ok = read_stream_bounded(p.read_fd(), buf, 10, truncated);
    EXPECT_TRUE(ok);
    EXPECT_TRUE(truncated);
    EXPECT_EQ(buf.size(), 10U);
    EXPECT_EQ(buf, "0123456789");

    // Invalid fd handling
    std::string dummy;
    bool dummy_trunc = false;
    EXPECT_FALSE(read_stream_bounded(-1, dummy, 10, dummy_trunc));
}

TEST(ProcessTest, MonotonicTimeAdvances) {
    uint64_t t1 = get_monotonic_time_ms();
    ::usleep(5000); // 5 ms sleep
    uint64_t t2 = get_monotonic_time_ms();

    EXPECT_GT(t1, 0);
    EXPECT_GE(t2, t1);
}

TEST(ProcessTest, CloseFdsExceptPreservesTargets) {
    int p[2];
    ASSERT_EQ(::pipe(p), 0);

    close_fds_except({p[0], p[1], STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO});

    // p[0] and p[1] should still be valid
    EXPECT_GE(fcntl(p[0], F_GETFD), 0);
    EXPECT_GE(fcntl(p[1], F_GETFD), 0);

    ::close(p[0]);
    ::close(p[1]);
}

TEST(ProcessTest, ReadStreamBoundedNormalNoTruncation) {
    ScopedPipe p;
    ASSERT_GE(p.read_fd(), 0);
    ASSERT_GE(p.write_fd(), 0);

    std::string test_data = "normal_read_data";
    ASSERT_EQ(::write(p.write_fd(), test_data.data(), test_data.size()), static_cast<ssize_t>(test_data.size()));
    p.close_write();

    std::string buf;
    bool truncated = false;
    bool ok = read_stream_bounded(p.read_fd(), buf, 1024, truncated);
    EXPECT_TRUE(ok);
    EXPECT_FALSE(truncated);
    EXPECT_EQ(buf, "normal_read_data");
}

TEST(ProcessTest, CloseFdsExceptWithGapsInPreservedList) {
    int p1[2], p2[2];
    ASSERT_EQ(::pipe(p1), 0);
    ASSERT_EQ(::pipe(p2), 0);

    // Call with sorted preserved FDs with gaps to exercise close_range ranges
    close_fds_except({STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO, p1[0], p2[1]});

    EXPECT_GE(fcntl(p1[0], F_GETFD), 0);
    EXPECT_GE(fcntl(p2[1], F_GETFD), 0);

    ::close(p1[0]);
    ::close(p1[1]);
    ::close(p2[0]);
    ::close(p2[1]);
}

