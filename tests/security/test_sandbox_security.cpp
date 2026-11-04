#include <gtest/gtest.h>
#include "core/supervisor/supervisor.hpp"
#include "core/supervisor/config.hpp"

using namespace runbox::supervisor;
using namespace runbox::monitoring;

TEST(SecurityAcceptanceTest, BlockHostNetworkAccess) {
    JobConfig cfg;
    cfg.execution_id = "test-sec-network";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c",
        "import socket\n"
        "try:\n"
        "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "    s.settimeout(1)\n"
        "    s.connect(('8.8.8.8', 53))\n"
        "    print('CONNECTED_UNEXPECTED')\n"
        "except Exception as e:\n"
        "    print(f'NETWORK_BLOCKED:{type(e).__name__}')\n"
    };
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.stdout_output.find("CONNECTED_UNEXPECTED"), std::string::npos);
    EXPECT_NE(res.stdout_output.find("NETWORK_BLOCKED"), std::string::npos);
}

TEST(SecurityAcceptanceTest, BlockHostFilesystemWrite) {
    JobConfig cfg;
    cfg.execution_id = "test-sec-fs-write";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c",
        "try:\n"
        "    with open('/etc/runbox_exploit', 'w') as f:\n"
        "        f.write('pwn')\n"
        "    print('WRITE_UNEXPECTED')\n"
        "except Exception as e:\n"
        "    print(f'WRITE_BLOCKED:{type(e).__name__}')\n"
    };
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.stdout_output.find("WRITE_UNEXPECTED"), std::string::npos);
    EXPECT_NE(res.stdout_output.find("WRITE_BLOCKED"), std::string::npos);
}

TEST(SecurityAcceptanceTest, BlockHostEtcShadowRead) {
    JobConfig cfg;
    cfg.execution_id = "test-sec-shadow";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c",
        "try:\n"
        "    with open('/etc/shadow', 'r') as f:\n"
        "        print('SHADOW_LEAKED')\n"
        "except Exception as e:\n"
        "    print(f'SHADOW_BLOCKED:{type(e).__name__}')\n"
    };
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.stdout_output.find("SHADOW_LEAKED"), std::string::npos);
    EXPECT_NE(res.stdout_output.find("SHADOW_BLOCKED"), std::string::npos);
}

TEST(SecurityAcceptanceTest, BlockChrootEscape) {
    JobConfig cfg;
    cfg.execution_id = "test-sec-escape";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c",
        "import os\n"
        "try:\n"
        "    files = os.listdir('../../../../../root')\n"
        "    print('ESCAPE_SUCCESS')\n"
        "except Exception as e:\n"
        "    print(f'ESCAPE_BLOCKED:{type(e).__name__}')\n"
    };
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_EQ(res.stdout_output.find("ESCAPE_SUCCESS"), std::string::npos);
    EXPECT_NE(res.stdout_output.find("ESCAPE_BLOCKED"), std::string::npos);
}

TEST(SecurityAcceptanceTest, BlockHostEnvironmentLeakage) {
    JobConfig cfg;
    cfg.execution_id = "test-sec-env";
    cfg.language = "python";
    cfg.executable_path = "/usr/bin/python3";
    cfg.argv = {"-c",
        "import os\n"
        "leaks = [k for k in os.environ if 'SECRET' in k or 'TOKEN' in k or 'KEY' in k]\n"
        "print('LEAKS:', leaks)\n"
    };
    cfg.limits.timeout_ms = 4000;

    Supervisor sup;
    auto res = sup.execute_job(cfg);

    EXPECT_EQ(res.exit_code, 0);
    EXPECT_NE(res.stdout_output.find("LEAKS: []"), std::string::npos);
}
