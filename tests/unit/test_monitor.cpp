#include <gtest/gtest.h>
#include "core/monitoring/monitor.hpp"
#include <unistd.h>

using namespace runbox::monitoring;

TEST(MonitorTest, TerminationReasonStringConversion) {
    EXPECT_EQ(to_string(TerminationReason::NormalExit), "normal_exit");
    EXPECT_EQ(to_string(TerminationReason::NonZeroExit), "non_zero_exit");
    EXPECT_EQ(to_string(TerminationReason::TimedOut), "timed_out");
    EXPECT_EQ(to_string(TerminationReason::MemoryLimitExceeded), "memory_limit_exceeded");
    EXPECT_EQ(to_string(TerminationReason::ProcessLimitExceeded), "process_limit_exceeded");
    EXPECT_EQ(to_string(TerminationReason::OutputLimitExceeded), "output_limit_exceeded");
    EXPECT_EQ(to_string(TerminationReason::SecurityViolation), "security_violation");
    EXPECT_EQ(to_string(TerminationReason::SignalTerminated), "signal_terminated");
    EXPECT_EQ(to_string(TerminationReason::InternalError), "internal_error");
}

TEST(MonitorTest, StreamConsumerTruncation) {
    int p[2];
    ASSERT_EQ(::pipe(p), 0);

    StreamConsumer consumer(p[0], -1, 50); // 50 bytes limit
    consumer.start();

    std::string large_chunk(200, 'X');
    ssize_t written = ::write(p[1], large_chunk.data(), large_chunk.size());
    ASSERT_EQ(written, static_cast<ssize_t>(large_chunk.size()));
    ::close(p[1]);

    consumer.wait_until_closed(1000);
    ::close(p[0]);

    EXPECT_LE(consumer.get_stdout().size(), 50);
    EXPECT_TRUE(consumer.is_stdout_truncated());
    EXPECT_EQ(consumer.get_stdout_bytes(), 200);
}

TEST(MonitorTest, StreamConsumerSmallBufferNoTruncation) {
    int p[2];
    ASSERT_EQ(::pipe(p), 0);

    StreamConsumer consumer(p[0], -1, 1024);
    consumer.start();

    std::string msg = "Hello Runbox Monitor\n";
    ssize_t written = ::write(p[1], msg.data(), msg.size());
    ASSERT_EQ(written, static_cast<ssize_t>(msg.size()));
    ::close(p[1]);

    consumer.wait_until_closed(1000);
    ::close(p[0]);

    EXPECT_EQ(consumer.get_stdout(), msg);
    EXPECT_FALSE(consumer.is_stdout_truncated());
    EXPECT_EQ(consumer.get_stdout_bytes(), msg.size());
}

TEST(MonitorTest, StreamConsumerBothStdoutAndStderr) {
    int p_out[2];
    int p_err[2];
    ASSERT_EQ(::pipe(p_out), 0);
    ASSERT_EQ(::pipe(p_err), 0);

    StreamConsumer consumer(p_out[0], p_err[0], 256);
    consumer.start();

    std::string out_msg = "stdout stream test\n";
    std::string err_msg = "stderr error stream test\n";

    EXPECT_EQ(::write(p_out[1], out_msg.data(), out_msg.size()), static_cast<ssize_t>(out_msg.size()));
    EXPECT_EQ(::write(p_err[1], err_msg.data(), err_msg.size()), static_cast<ssize_t>(err_msg.size()));

    ::close(p_out[1]);
    ::close(p_err[1]);

    consumer.wait_until_closed(1000);
    ::close(p_out[0]);
    ::close(p_err[0]);

    EXPECT_EQ(consumer.get_stdout(), out_msg);
    EXPECT_EQ(consumer.get_stderr(), err_msg);
    EXPECT_FALSE(consumer.is_stdout_truncated());
    EXPECT_FALSE(consumer.is_stderr_truncated());
}

TEST(MonitorTest, StreamConsumerHandlesInvalidFdsGracefully) {
    StreamConsumer consumer(-1, -1, 1024);
    consumer.start();
    consumer.wait_until_closed(100);
    EXPECT_TRUE(consumer.get_stdout().empty());
    EXPECT_TRUE(consumer.get_stderr().empty());
}
