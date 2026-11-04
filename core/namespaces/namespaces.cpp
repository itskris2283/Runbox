#include "core/namespaces/namespaces.hpp"

#include <sched.h>
#include <unistd.h>
#include <sys/mount.h>
#include <fcntl.h>
#include <fstream>
#include <sstream>
#include <cstring>
#include <iostream>

namespace runbox::namespaces {

NamespaceManager::NamespaceManager(NamespaceConfig config)
    : config_(std::move(config)) {}

int NamespaceManager::get_clone_flags() const noexcept {
    int flags = 0;
    if (config_.enable_user)  flags |= CLONE_NEWUSER;
    if (config_.enable_pid)   flags |= CLONE_NEWPID;
    if (config_.enable_mount) flags |= CLONE_NEWNS;
    if (config_.enable_net)   flags |= CLONE_NEWNET;
    if (config_.enable_ipc)   flags |= CLONE_NEWIPC;
    if (config_.enable_uts)   flags |= CLONE_NEWUTS;
    return flags;
}

bool NamespaceManager::unshare_namespaces() {
    int flags = get_clone_flags();
    if (flags != 0) {
        if (::unshare(flags) != 0) {
            std::cerr << "[runbox::namespaces] unshare failed: " << strerror(errno) << "\n";
            return false;
        }
    }
    return true;
}

bool NamespaceManager::setup_private_mounts() {
    if (config_.enable_mount) {
        // Prevent host mount changes from propagating into the sandbox and vice versa
        if (::mount(nullptr, "/", nullptr, MS_REC | MS_PRIVATE, nullptr) != 0) {
            std::cerr << "[runbox::namespaces] mount MS_PRIVATE failed: " << strerror(errno) << "\n";
            return false;
        }
    }

    if (config_.enable_uts) {
        if (!configure_hostname()) {
            return false;
        }
    }

    return true;
}

bool NamespaceManager::write_id_mappings(pid_t target_pid, uid_t outside_uid, gid_t outside_gid,
                                        uid_t inside_uid, gid_t inside_gid) {
    std::string pid_str = (target_pid == 0) ? "self" : std::to_string(target_pid);

    // Disable setgroups first (mandatory on Linux for unprivileged gid mapping)
    std::string setgroups_path = "/proc/" + pid_str + "/setgroups";
    {
        std::ofstream sg_file(setgroups_path);
        if (sg_file.is_open()) {
            sg_file << "deny\n";
            sg_file.close();
        }
    }

    // Write gid_map: <inside_gid> <outside_gid> 1
    std::string gid_map_path = "/proc/" + pid_str + "/gid_map";
    {
        std::ofstream gm_file(gid_map_path);
        if (!gm_file.is_open()) {
            std::cerr << "[runbox::namespaces] open gid_map failed: " << strerror(errno) << "\n";
            return false;
        }
        gm_file << inside_gid << " " << outside_gid << " 1\n";
    }

    // Write uid_map: <inside_uid> <outside_uid> 1
    std::string uid_map_path = "/proc/" + pid_str + "/uid_map";
    {
        std::ofstream um_file(uid_map_path);
        if (!um_file.is_open()) {
            std::cerr << "[runbox::namespaces] open uid_map failed: " << strerror(errno) << "\n";
            return false;
        }
        um_file << inside_uid << " " << outside_uid << " 1\n";
    }

    return true;
}

bool NamespaceManager::configure_hostname() {
    if (::sethostname(config_.hostname.c_str(), config_.hostname.length()) != 0) {
        return false;
    }
    return true;
}

bool NamespaceManager::verify_isolation() const {
    if (config_.enable_uts) {
        char buf[256];
        if (::gethostname(buf, sizeof(buf)) == 0) {
            if (config_.hostname != buf) {
                return false;
            }
        }
    }
    return true;
}

} // namespace runbox::namespaces
