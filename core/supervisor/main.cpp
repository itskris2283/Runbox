#include "core/supervisor/supervisor.hpp"
#include "core/supervisor/config.hpp"
#include "core/monitoring/monitor.hpp"

#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>

static std::string escape_json_str(const std::string& s) {
    std::ostringstream o;
    for (char c : s) {
        if (c == '"') o << "\\\"";
        else if (c == '\\') o << "\\\\";
        else if (c == '\b') o << "\\b";
        else if (c == '\f') o << "\\f";
        else if (c == '\n') o << "\\n";
        else if (c == '\r') o << "\\r";
        else if (c == '\t') o << "\\t";
        else if (static_cast<unsigned char>(c) <= 0x1f) {
            o << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
        } else {
            o << c;
        }
    }
    return o.str();
}

static std::string result_to_json(const runbox::monitoring::ExecutionResult& res) {
    std::ostringstream ss;
    ss << "{\n"
       << "  \"execution_id\": \"" << escape_json_str(res.execution_id) << "\",\n"
       << "  \"exit_code\": " << res.exit_code << ",\n"
       << "  \"status\": \"" << (res.exit_code == 0 && res.reason == runbox::monitoring::TerminationReason::NormalExit ? "completed" : "failed") << "\",\n"
       << "  \"termination_reason\": \"" << runbox::monitoring::to_string(res.reason) << "\",\n"
       << "  \"stdout\": \"" << escape_json_str(res.stdout_output) << "\",\n"
       << "  \"stderr\": \"" << escape_json_str(res.stderr_output) << "\",\n"
       << "  \"stdout_truncated\": " << (res.stdout_truncated ? "true" : "false") << ",\n"
       << "  \"stderr_truncated\": " << (res.stderr_truncated ? "true" : "false") << ",\n"
       << "  \"stdout_bytes\": " << res.stdout_bytes << ",\n"
       << "  \"stderr_bytes\": " << res.stderr_bytes << ",\n"
       << "  \"resource_usage\": {\n"
       << "    \"wall_time_ms\": " << res.wall_time_ms << ",\n"
       << "    \"cpu_time_ms\": " << res.cpu_time_ms << ",\n"
       << "    \"memory_peak_bytes\": " << res.memory_peak_bytes << ",\n"
       << "    \"pids_peak\": " << res.pids_peak << ",\n"
       << "    \"oom_killed\": " << (res.oom_killed ? "true" : "false") << "\n"
       << "  }\n"
       << "}";
    return ss.str();
}

int main(int argc, char* argv[]) {
    std::string config_json;
    std::string output_file;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--config" && i + 1 < argc) {
            std::string config_path = argv[++i];
            std::ifstream f(config_path);
            if (!f.is_open()) {
                std::cerr << "{\"error\": \"Could not open config file: " << config_path << "\"}\n";
                return 1;
            }
            std::stringstream buf;
            buf << f.rdbuf();
            config_json = buf.str();
        } else if (arg == "--json" && i + 1 < argc) {
            config_json = argv[++i];
        } else if (arg == "--output" && i + 1 < argc) {
            output_file = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: runbox-supervisor --config <path_to_config.json> [--output <result.json>]\n"
                      << "       runbox-supervisor --json '<json_string>' [--output <result.json>]\n";
            return 0;
        }
    }

    if (config_json.empty()) {
        // Read from stdin
        std::stringstream buf;
        buf << std::cin.rdbuf();
        config_json = buf.str();
    }

    if (config_json.empty()) {
        std::cerr << "{\"error\": \"No job configuration provided\"}\n";
        return 1;
    }

    runbox::supervisor::JobConfig config = runbox::supervisor::JobConfig::from_json(config_json);
    if (config.execution_id.empty()) {
        config.execution_id = "job-" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
    }

    std::string val_err;
    if (!config.validate(val_err)) {
        std::cerr << "{\"error\": \"Validation rejected by supervisor: " << val_err << "\"}\n";
        return 1;
    }

    runbox::supervisor::Supervisor supervisor;
    auto result = supervisor.execute_job(config);
    std::string json_out = result_to_json(result);

    if (!output_file.empty()) {
        std::ofstream out(output_file);
        if (out.is_open()) {
            out << json_out << "\n";
        }
    }

    std::cout << json_out << std::endl;
    return 0;
}
