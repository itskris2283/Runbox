#pragma once

#include <string>
#include <vector>
#include <cstdint>
#include <sys/types.h>

namespace runbox::security {

struct SecurityLimits {
    uint32_t cpu_seconds = 10;
    uint64_t as_limit_bytes = 256ULL * 1024ULL * 1024ULL; // 256 MB AS limit
    uint64_t fsize_limit_bytes = 16ULL * 1024ULL * 1024ULL; // 16 MB max file
    uint32_t max_pids = 64;
    uint32_t max_fds = 64;
};

class PrivilegeManager {
public:
    explicit PrivilegeManager(SecurityLimits limits = {});
    ~PrivilegeManager() = default;

    // Sets PR_SET_NO_NEW_PRIVS
    bool enable_no_new_privs();

    // Sets POSIX resource limits via setrlimit
    bool apply_rlimits();

    // Drops all POSIX capabilities
    bool drop_capabilities();

    // Changes process identity to unprivileged UID/GID and removes supplementary groups
    bool drop_identity(uid_t target_uid, gid_t target_gid);

    // Verifies that capabilities, no_new_privs, supplementary groups, and identity are dropped
    [[nodiscard]] bool verify_privileges_dropped(uid_t target_uid, gid_t target_gid) const;

    // Constructs sanitized, safe environment variables list
    [[nodiscard]] std::vector<std::string> build_safe_environment() const;

private:
    SecurityLimits limits_;
};

} // namespace runbox::security
