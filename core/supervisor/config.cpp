#include "core/supervisor/config.hpp"

#include <sstream>
#include <iomanip>
#include <algorithm>
#include <cctype>

namespace runbox::supervisor {

// Simple, self-contained JSON helper for typed JobConfig parsing
static std::string extract_string_field(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return "";

    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return "";

    size_t start = json.find('"', pos);
    if (start == std::string::npos) return "";

    std::string result;
    bool escape = false;
    for (size_t i = start + 1; i < json.size(); ++i) {
        char c = json[i];
        if (escape) {
            if (c == 'n') result += '\n';
            else if (c == 'r') result += '\r';
            else if (c == 't') result += '\t';
            else if (c == '"') result += '"';
            else if (c == '\\') result += '\\';
            else result += c;
            escape = false;
        } else if (c == '\\') {
            escape = true;
        } else if (c == '"') {
            break;
        } else {
            result += c;
        }
    }
    return result;
}

static uint64_t extract_uint_field(const std::string& json, const std::string& key, uint64_t default_val) {
    std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return default_val;

    pos = json.find(':', pos + pattern.size());
    if (pos == std::string::npos) return default_val;

    size_t start = pos + 1;
    while (start < json.size() && (std::isspace(json[start]) || json[start] == '"')) {
        start++;
    }
    size_t end = start;
    while (end < json.size() && (std::isdigit(json[end]))) {
        end++;
    }
    if (start == end) return default_val;
    try {
        return std::stoull(json.substr(start, end - start));
    } catch (...) {
        return default_val;
    }
}

static std::vector<std::string> extract_string_array(const std::string& json, const std::string& key) {
    std::vector<std::string> results;
    std::string pattern = "\"" + key + "\"";
    size_t pos = json.find(pattern);
    if (pos == std::string::npos) return results;

    pos = json.find('[', pos);
    if (pos == std::string::npos) return results;

    size_t array_end = json.find(']', pos);
    if (array_end == std::string::npos) return results;

    size_t current = pos + 1;
    while (current < array_end) {
        size_t start = json.find('"', current);
        if (start == std::string::npos || start >= array_end) break;

        std::string elem;
        bool escape = false;
        size_t next_pos = start + 1;
        for (; next_pos < array_end; ++next_pos) {
            char c = json[next_pos];
            if (escape) {
                if (c == 'n') elem += '\n';
                else if (c == 't') elem += '\t';
                else if (c == '"') elem += '"';
                else if (c == '\\') elem += '\\';
                else elem += c;
                escape = false;
            } else if (c == '\\') {
                escape = true;
            } else if (c == '"') {
                break;
            } else {
                elem += c;
            }
        }
        results.push_back(elem);
        current = next_pos + 1;
    }
    return results;
}

JobConfig JobConfig::from_json(const std::string& json) {
    JobConfig cfg;
    cfg.execution_id = extract_string_field(json, "execution_id");
    cfg.language = extract_string_field(json, "language");
    cfg.executable_path = extract_string_field(json, "executable_path");
    cfg.workspace_dir = extract_string_field(json, "workspace_dir");
    cfg.stdin_data = extract_string_field(json, "stdin");

    cfg.argv = extract_string_array(json, "argv");
    cfg.env = extract_string_array(json, "env");

    cfg.limits.timeout_ms = extract_uint_field(json, "timeout_ms", 3000);
    cfg.limits.memory_mb = extract_uint_field(json, "memory_mb", 128);
    cfg.limits.cpu_quota_percent = static_cast<uint32_t>(extract_uint_field(json, "cpu_quota_percent", 50));
    cfg.limits.process_limit = static_cast<uint32_t>(extract_uint_field(json, "process_limit", 32));
    cfg.limits.output_limit_bytes = extract_uint_field(json, "output_limit_bytes", 1048576);

    return cfg;
}

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

std::string JobConfig::to_json() const {
    std::ostringstream ss;
    ss << "{\n"
       << "  \"execution_id\": \"" << escape_json_str(execution_id) << "\",\n"
       << "  \"language\": \"" << escape_json_str(language) << "\",\n"
       << "  \"executable_path\": \"" << escape_json_str(executable_path) << "\",\n"
       << "  \"workspace_dir\": \"" << escape_json_str(workspace_dir) << "\",\n"
       << "  \"stdin\": \"" << escape_json_str(stdin_data) << "\",\n"
       << "  \"argv\": [";
    for (size_t i = 0; i < argv.size(); ++i) {
        ss << "\"" << escape_json_str(argv[i]) << "\"" << (i + 1 < argv.size() ? ", " : "");
    }
    ss << "],\n  \"limits\": {\n"
       << "    \"timeout_ms\": " << limits.timeout_ms << ",\n"
       << "    \"memory_mb\": " << limits.memory_mb << ",\n"
       << "    \"cpu_quota_percent\": " << limits.cpu_quota_percent << ",\n"
       << "    \"process_limit\": " << limits.process_limit << ",\n"
       << "    \"output_limit_bytes\": " << limits.output_limit_bytes << "\n"
       << "  }\n}";
    return ss.str();
}

bool JobConfig::validate(std::string& err) const {
    // 1. Execution ID validation
    if (execution_id.empty() || execution_id.length() > 64) {
        err = "execution_id must be between 1 and 64 characters";
        return false;
    }
    for (char c : execution_id) {
        if (!std::isalnum(static_cast<unsigned char>(c)) && c != '-' && c != '_') {
            err = "execution_id contains illegal characters (only alphanumeric, '-', '_' permitted)";
            return false;
        }
    }

    // 2. Language validation
    if (language != "python" && language != "python3" &&
        language != "cpp" && language != "cpp_compile" &&
        language != "minimal") {
        err = "language '" + language + "' is not supported by sandbox supervisor";
        return false;
    }

    // 3. Executable path validation (must be absolute, no traversal)
    if (executable_path.empty() || executable_path[0] != '/') {
        err = "executable_path must be an absolute path";
        return false;
    }
    if (executable_path.find("..") != std::string::npos) {
        err = "executable_path contains illegal path traversal '..'";
        return false;
    }

    bool is_whitelisted = false;
    const std::vector<std::string> allowed_prefixes = {
        "/usr/bin/", "/bin/", "/workspace/", "/sandbox/workspace/"
    };
    for (const auto& prefix : allowed_prefixes) {
        if (executable_path.rfind(prefix, 0) == 0) {
            is_whitelisted = true;
            break;
        }
    }
    if (!workspace_dir.empty() && executable_path.rfind(workspace_dir, 0) == 0) {
        is_whitelisted = true;
    }

    if (!is_whitelisted) {
        err = "executable_path '" + executable_path + "' is outside permitted execution directories";
        return false;
    }

    // 4. Workspace dir validation (optional: empty means ephemeral in-memory tmpfs)
    if (!workspace_dir.empty()) {
        if (workspace_dir[0] != '/') {
            err = "workspace_dir must be an absolute path";
            return false;
        }
        if (workspace_dir.find("..") != std::string::npos) {
            err = "workspace_dir contains illegal path traversal '..'";
            return false;
        }
    }

    // 5. Limits bounds validation
    if (limits.timeout_ms < 10 || limits.timeout_ms > 60000) {
        err = "timeout_ms out of range [10, 60000]";
        return false;
    }
    if (limits.memory_mb < 16 || limits.memory_mb > 2048) {
        err = "memory_mb out of range [16, 2048]";
        return false;
    }
    if (limits.cpu_quota_percent < 1 || limits.cpu_quota_percent > 100) {
        err = "cpu_quota_percent out of range [1, 100]";
        return false;
    }
    if (limits.process_limit < 1 || limits.process_limit > 128) {
        err = "process_limit out of range [1, 128]";
        return false;
    }
    if (limits.output_limit_bytes < 1024 || limits.output_limit_bytes > 10485760) {
        err = "output_limit_bytes out of range [1024, 10485760]";
        return false;
    }

    return true;
}

} // namespace runbox::supervisor
