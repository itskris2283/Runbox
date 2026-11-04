#pragma once

#include <string>
#include <vector>
#include <sys/types.h>

namespace runbox::namespaces {

struct NamespaceConfig {
    bool enable_pid = true;
    bool enable_mount = true;
    bool enable_net = true;
    bool enable_ipc = true;
    bool enable_uts = true;
    bool enable_user = true;
    std::string hostname = "runbox";
    uid_t inner_uid = 0;
    gid_t inner_gid = 0;
};

class NamespaceManager {
public:
    explicit NamespaceManager(NamespaceConfig config = {});
    ~NamespaceManager() = default;

    // Returns unshare clone flags for the requested namespaces
    [[nodiscard]] int get_clone_flags() const noexcept;

    // Executes unshare() with configured flags inside child process
    bool unshare_namespaces();

    // Sets up private mount propagation after user namespace mappings are established
    bool setup_private_mounts();

    // Sets up uid/gid mappings for a child process that entered a user namespace
    // Must be called by parent on child_pid, or inside child with appropriate permissions
    static bool write_id_mappings(pid_t target_pid, uid_t outside_uid, gid_t outside_gid,
                                 uid_t inside_uid, gid_t inside_gid);

    // Configures UTS hostname
    bool configure_hostname();

    // Verifies that namespaces were successfully established
    [[nodiscard]] bool verify_isolation() const;

private:
    NamespaceConfig config_;
};

} // namespace runbox::namespaces
