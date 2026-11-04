#pragma once

#include <string>
#include <vector>

namespace runbox::filesystem {

struct MountEntry {
    std::string source;
    std::string target;
    std::string fstype;
    unsigned long flags = 0;
    std::string data;
};

struct FilesystemConfig {
    std::string host_workspace_dir;
    std::string sandbox_root_dir;
    bool enable_landlock = true;
    bool mount_proc = true;
    bool mount_dev = true;
    bool mount_tmp = true;
};

class FilesystemManager {
public:
    explicit FilesystemManager(FilesystemConfig config);
    ~FilesystemManager() = default;

    // Sets up isolated sandbox directory tree, mounts, and chroot/pivot_root
    bool setup_sandbox_filesystem();

    // Applies Landlock filesystem access restrictions if supported
    bool apply_landlock_rules();

    // Cleans up sandbox mounts and directories
    bool teardown_sandbox();

    // Sets up minimal /dev nodes inside sandbox
    bool create_minimal_dev();

    // Sets up mounts inside sandbox directory tree
    bool setup_mounts();

    [[nodiscard]] const std::string& get_sandbox_root() const noexcept { return config_.sandbox_root_dir; }
    [[nodiscard]] const std::string& get_workspace() const noexcept { return config_.host_workspace_dir; }

private:
    FilesystemConfig config_;
};

} // namespace runbox::filesystem
