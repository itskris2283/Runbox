#include "core/security/privileges.hpp"

#include <sys/prctl.h>
#include <sys/resource.h>
#include <unistd.h>
#include <grp.h>
#include <cstring>
#include <iostream>

#ifndef PR_CAPBSET_DROP
#define PR_CAPBSET_DROP 24
#endif
#ifndef PR_CAPBSET_READ
#define PR_CAPBSET_READ 23
#endif
#ifndef PR_CAP_AMBIENT
#define PR_CAP_AMBIENT 47
#endif
#ifndef PR_CAP_AMBIENT_CLEAR_ALL
#define PR_CAP_AMBIENT_CLEAR_ALL 4
#endif

namespace runbox::security {

PrivilegeManager::PrivilegeManager(SecurityLimits limits)
    : limits_(limits) {}

bool PrivilegeManager::enable_no_new_privs() {
    if (::prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        std::cerr << "[runbox::security] prctl(PR_SET_NO_NEW_PRIVS) failed: " << strerror(errno) << "\n";
        return false;
    }
    return true;
}

bool PrivilegeManager::apply_rlimits() {
    struct rlimit rl{};

    // CPU limit (seconds)
    if (limits_.cpu_seconds > 0) {
        rl.rlim_cur = limits_.cpu_seconds;
        rl.rlim_max = limits_.cpu_seconds + 1;
        ::setrlimit(RLIMIT_CPU, &rl);
    }

    // Address space (memory)
    if (limits_.as_limit_bytes > 0) {
        rl.rlim_cur = limits_.as_limit_bytes;
        rl.rlim_max = limits_.as_limit_bytes;
        ::setrlimit(RLIMIT_AS, &rl);
    }

    // Max file size
    if (limits_.fsize_limit_bytes > 0) {
        rl.rlim_cur = limits_.fsize_limit_bytes;
        rl.rlim_max = limits_.fsize_limit_bytes;
        ::setrlimit(RLIMIT_FSIZE, &rl);
    }

    // Max processes
    if (limits_.max_pids > 0) {
        rl.rlim_cur = limits_.max_pids;
        rl.rlim_max = limits_.max_pids;
        ::setrlimit(RLIMIT_NPROC, &rl);
    }

    // Max open file descriptors
    if (limits_.max_fds > 0) {
        rl.rlim_cur = limits_.max_fds;
        rl.rlim_max = limits_.max_fds;
        ::setrlimit(RLIMIT_NOFILE, &rl);
    }

    // Prevent core dumps containing potentially sensitive execution memory
    rl.rlim_cur = 0;
    rl.rlim_max = 0;
    ::setrlimit(RLIMIT_CORE, &rl);

    return true;
}

bool PrivilegeManager::drop_capabilities() {
    // 1. Clear all ambient capabilities
    ::prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0);

    // 2. Drop all bounding capabilities
    for (int cap = 0; cap <= 63; ++cap) {
        if (::prctl(PR_CAPBSET_READ, cap, 0, 0, 0) >= 0) {
            ::prctl(PR_CAPBSET_DROP, cap, 0, 0, 0);
        }
    }

    return true;
}

bool PrivilegeManager::drop_identity(uid_t target_uid, gid_t target_gid) {
    // 1. Remove all supplementary groups
    if (::setgroups(0, nullptr) != 0) {
        // If unprivileged in user namespace, setgroups may fail or be denied by /proc/self/setgroups
    }

    // 2. Transition GID and UID
    if (::setresgid(target_gid, target_gid, target_gid) != 0) {
        std::cerr << "[runbox::security] setresgid failed: " << strerror(errno) << "\n";
        return false;
    }
    if (::setresuid(target_uid, target_uid, target_uid) != 0) {
        std::cerr << "[runbox::security] setresuid failed: " << strerror(errno) << "\n";
        return false;
    }
    return true;
}

bool PrivilegeManager::verify_privileges_dropped(uid_t target_uid, gid_t target_gid) const {
    if (::getuid() != target_uid || ::geteuid() != target_uid) {
        return false;
    }
    if (::getgid() != target_gid || ::getegid() != target_gid) {
        return false;
    }
    if (::prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) {
        return false;
    }
    return true;
}

std::vector<std::string> PrivilegeManager::build_safe_environment() const {
    return {
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "HOME=/tmp",
        "TMPDIR=/tmp",
        "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1"
    };
}

} // namespace runbox::security
