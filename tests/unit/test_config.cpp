#include <gtest/gtest.h>
#include "core/supervisor/config.hpp"

using namespace runbox::supervisor;

TEST(ConfigTest, ParseValidJson) {
    std::string json = R"JSON({
        "execution_id": "test-1234",
        "language": "python",
        "executable_path": "/usr/bin/python3",
        "argv": ["-c", "print('hello')"],
        "stdin": "input_data",
        "limits": {
            "timeout_ms": 5000,
            "memory_mb": 256,
            "cpu_quota_percent": 75,
            "process_limit": 16,
            "output_limit_bytes": 2048
        }
    })JSON";

    JobConfig cfg = JobConfig::from_json(json);
    EXPECT_EQ(cfg.execution_id, "test-1234");
    EXPECT_EQ(cfg.language, "python");
    EXPECT_EQ(cfg.executable_path, "/usr/bin/python3");
    ASSERT_EQ(cfg.argv.size(), 2);
    EXPECT_EQ(cfg.argv[0], "-c");
    EXPECT_EQ(cfg.argv[1], "print('hello')");
    EXPECT_EQ(cfg.stdin_data, "input_data");
    EXPECT_EQ(cfg.limits.timeout_ms, 5000);
    EXPECT_EQ(cfg.limits.memory_mb, 256);
    EXPECT_EQ(cfg.limits.cpu_quota_percent, 75);
    EXPECT_EQ(cfg.limits.process_limit, 16);
    EXPECT_EQ(cfg.limits.output_limit_bytes, 2048);
}

TEST(ConfigTest, DefaultValuesOnEmptyJson) {
    JobConfig cfg = JobConfig::from_json("{}");
    EXPECT_EQ(cfg.limits.timeout_ms, 3000);
    EXPECT_EQ(cfg.limits.memory_mb, 128);
    EXPECT_EQ(cfg.limits.cpu_quota_percent, 50);
    EXPECT_EQ(cfg.limits.process_limit, 32);
    EXPECT_EQ(cfg.limits.output_limit_bytes, 1048576);
}

TEST(ConfigTest, SerializationRoundTrip) {
    JobConfig original;
    original.execution_id = "rt-test";
    original.language = "cpp";
    original.executable_path = "/usr/bin/gcc";
    original.argv = {"-O2", "main.cpp"};
    original.stdin_data = "stdin_payload";
    original.limits.timeout_ms = 4000;
    original.limits.memory_mb = 512;

    std::string json = original.to_json();
    JobConfig parsed = JobConfig::from_json(json);

    EXPECT_EQ(parsed.execution_id, original.execution_id);
    EXPECT_EQ(parsed.language, original.language);
    EXPECT_EQ(parsed.executable_path, original.executable_path);
    EXPECT_EQ(parsed.stdin_data, original.stdin_data);
    EXPECT_EQ(parsed.limits.timeout_ms, original.limits.timeout_ms);
    EXPECT_EQ(parsed.limits.memory_mb, original.limits.memory_mb);
}

// Security Validation Tests (Section 3.2)
TEST(ConfigTest, ValidationPassesOnWellFormedConfig) {
    JobConfig cfg;
    cfg.execution_id = "job-valid_01";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/runbox_ws_test";
    cfg.limits.timeout_ms = 3000;
    cfg.limits.memory_mb = 128;
    cfg.limits.cpu_quota_percent = 50;
    cfg.limits.process_limit = 16;
    cfg.limits.output_limit_bytes = 65536;

    std::string err;
    EXPECT_TRUE(cfg.validate(err)) << "Error: " << err;
    EXPECT_TRUE(err.empty());
}

TEST(ConfigTest, ValidationRejectsEmptyOrLongExecutionId) {
    JobConfig cfg;
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.execution_id = "";
    EXPECT_FALSE(cfg.validate(err));

    cfg.execution_id = std::string(65, 'a');
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsIllegalCharactersInExecutionId) {
    JobConfig cfg;
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.execution_id = "job/with/slashes";
    EXPECT_FALSE(cfg.validate(err));

    cfg.execution_id = "job;rm -rf /";
    EXPECT_FALSE(cfg.validate(err));

    cfg.execution_id = "job..traversal";
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsUnsupportedLanguage) {
    JobConfig cfg;
    cfg.execution_id = "job-lang";
    cfg.executable_path = "/bin/sh";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.language = "ruby";
    EXPECT_FALSE(cfg.validate(err));

    cfg.language = "bash";
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsRelativeOrHostSensitiveExecutablePath) {
    JobConfig cfg;
    cfg.execution_id = "job-path";
    cfg.language = "python";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.executable_path = "python3"; // relative path
    EXPECT_FALSE(cfg.validate(err));

    cfg.executable_path = "/usr/bin/../bin/sh"; // path traversal
    EXPECT_FALSE(cfg.validate(err));

    cfg.executable_path = "/sbin/reboot"; // forbidden directory
    EXPECT_FALSE(cfg.validate(err));

    cfg.executable_path = "/etc/passwd"; // forbidden directory
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsWorkspacePathTraversal) {
    JobConfig cfg;
    cfg.execution_id = "job-ws";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";

    std::string err;
    cfg.workspace_dir = "relative/dir";
    EXPECT_FALSE(cfg.validate(err));

    cfg.workspace_dir = "/tmp/../root";
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsOutOfRangeLimits) {
    JobConfig cfg;
    cfg.execution_id = "job-limits";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.limits.timeout_ms = 5; // below min 10
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.timeout_ms = 3000;

    cfg.limits.memory_mb = 8; // below min 16
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.memory_mb = 128;

    cfg.limits.cpu_quota_percent = 0; // below min 1
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.cpu_quota_percent = 50;

    cfg.limits.process_limit = 0; // below min 1
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.process_limit = 32;

    cfg.limits.output_limit_bytes = 100; // below min 1024
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationRejectsAboveMaxLimits) {
    JobConfig cfg;
    cfg.execution_id = "job-limits-upper";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/ws";

    std::string err;
    cfg.limits.timeout_ms = 60001; // max 60000
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.timeout_ms = 3000;

    cfg.limits.memory_mb = 2049; // max 2048
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.memory_mb = 128;

    cfg.limits.cpu_quota_percent = 101; // max 100
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.cpu_quota_percent = 50;

    cfg.limits.process_limit = 129; // max 128
    EXPECT_FALSE(cfg.validate(err));
    cfg.limits.process_limit = 32;

    cfg.limits.output_limit_bytes = 10485761; // max 10485760
    EXPECT_FALSE(cfg.validate(err));
}

TEST(ConfigTest, ValidationAcceptsAlternateLanguagesAndWorkspacePrefix) {
    JobConfig cfg;
    cfg.execution_id = "job-lang-alt";
    cfg.language = "python3";
    cfg.workspace_dir = "/tmp/sandbox_ws";
    cfg.executable_path = "/tmp/sandbox_ws/my_script.py";
    std::string err;
    EXPECT_TRUE(cfg.validate(err));

    cfg.language = "cpp_compile";
    cfg.executable_path = "/sandbox/workspace/compile.sh";
    EXPECT_TRUE(cfg.validate(err));

    cfg.language = "minimal";
    cfg.executable_path = "/bin/ls";
    EXPECT_TRUE(cfg.validate(err));
}

TEST(ConfigTest, SerializationEscapesSpecialCharacters) {
    JobConfig cfg;
    cfg.execution_id = "job-esc";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.workspace_dir = "/tmp/ws";
    cfg.stdin_data = "Line1\nLine2\rLine3\t\"quotes\"\\backslash\b\f\x01";
    cfg.argv = {"arg1", "arg2\twith\\tab"};

    std::string json = cfg.to_json();
    EXPECT_NE(json.find("\\n"), std::string::npos);
    EXPECT_NE(json.find("\\r"), std::string::npos);
    EXPECT_NE(json.find("\\t"), std::string::npos);
    EXPECT_NE(json.find("\\\"quotes\\\""), std::string::npos);
    EXPECT_NE(json.find("\\\\backslash"), std::string::npos);
}

TEST(ConfigTest, DeserializationParsesEscapesAndHugeNumbers) {
    std::string json = R"JSON({
        "execution_id": "test_esc_json",
        "language": "python",
        "executable_path": "/usr/bin/python3",
        "stdin": "hello\tworld\r\"quoted\"\\slash\a",
        "argv": ["arg\"1", "arg\t2", "arg\\3", "arg\n4", "arg\a5"],
        "limits": {
            "timeout_ms": 99999999999999999999999999999999999999999999
        }
    })JSON";

    JobConfig cfg = JobConfig::from_json(json);
    EXPECT_EQ(cfg.execution_id, "test_esc_json");
    EXPECT_EQ(cfg.limits.timeout_ms, 3000); // Caught out_of_range and returned default_val
    ASSERT_EQ(cfg.argv.size(), 5);
}


