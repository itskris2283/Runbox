#include "core/filesystem/filesystem_isolation.hpp"

#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/prctl.h>
#include <unistd.h>
#include <fcntl.h>
#include <fstream>
#include <cstring>
#include <iostream>
#include <vector>

// Landlock ABI constants
#ifndef SYS_landlock_create_ruleset
#define SYS_landlock_create_ruleset 444
#endif
#ifndef SYS_landlock_add_rule
#define SYS_landlock_add_rule 445
#endif
#ifndef SYS_landlock_restrict_self
#define SYS_landlock_restrict_self 446
#endif

#ifndef LANDLOCK_CREATE_RULESET_VERSION
#define LANDLOCK_CREATE_RULESET_VERSION (1U << 0)
#endif

#ifndef LANDLOCK_RULE_PATH_BENEATH
#define LANDLOCK_RULE_PATH_BENEATH 1
#endif

struct landlock_ruleset_attr {
    uint64_t handled_access_fs;
};

struct landlock_path_beneath_attr {
    uint64_t allowed_access;
    int32_t parent_fd;
} __attribute__((packed));

#define LANDLOCK_ACCESS_FS_EXECUTE            (1ULL << 0)
#define LANDLOCK_ACCESS_FS_WRITE_FILE          (1ULL << 1)
#define LANDLOCK_ACCESS_FS_READ_FILE           (1ULL << 2)
#define LANDLOCK_ACCESS_FS_READ_DIR            (1ULL << 3)
#define LANDLOCK_ACCESS_FS_REMOVE_DIR          (1ULL << 4)
#define LANDLOCK_ACCESS_FS_REMOVE_FILE         (1ULL << 5)
#define LANDLOCK_ACCESS_FS_MAKE_CHAR           (1ULL << 6)
#define LANDLOCK_ACCESS_FS_MAKE_DIR            (1ULL << 7)
#define LANDLOCK_ACCESS_FS_MAKE_REG            (1ULL << 8)
#define LANDLOCK_ACCESS_FS_MAKE_SOCK           (1ULL << 9)
#define LANDLOCK_ACCESS_FS_MAKE_FIFO           (1ULL << 10)
#define LANDLOCK_ACCESS_FS_MAKE_BLOCK          (1ULL << 11)
#define LANDLOCK_ACCESS_FS_MAKE_SYM            (1ULL << 12)
#define LANDLOCK_ACCESS_FS_REFER               (1ULL << 13)
#define LANDLOCK_ACCESS_FS_TRUNCATE            (1ULL << 14)

namespace runbox::filesystem {

FilesystemManager::FilesystemManager(FilesystemConfig config)
    : config_(std::move(config)) {}

static bool make_dir_p(const std::string& path) {
    size_t pos = 0;
    while ((pos = path.find('/', pos + 1)) != std::string::npos) {
        std::string sub = path.substr(0, pos);
        if (!sub.empty()) {
            ::mkdir(sub.c_str(), 0755);
        }
    }
    return ::mkdir(path.c_str(), 0755) == 0 || errno == EEXIST;
}

static bool safe_bind_mount(const std::string& src, const std::string& dst, bool read_only) {
    struct stat st{};
    if (::stat(src.c_str(), &st) != 0) return true; // Source doesn't exist on host, skip

    if (S_ISDIR(st.st_mode)) {
        make_dir_p(dst);
    } else {
        size_t last_slash = dst.find_last_of('/');
        if (last_slash != std::string::npos) {
            make_dir_p(dst.substr(0, last_slash));
        }
        int fd = ::open(dst.c_str(), O_CREAT | O_WRONLY | O_CLOEXEC, 0644);
        if (fd >= 0) ::close(fd);
    }

    // Step 1: Initial recursive bind mount
    if (::mount(src.c_str(), dst.c_str(), nullptr, MS_BIND | MS_REC, nullptr) != 0) {
        return false;
    }

    // Step 2: Remount to enforce security flags (MS_NODEV, MS_NOSUID, and optionally MS_RDONLY)
    unsigned long remount_flags = MS_BIND | MS_REC | MS_REMOUNT | MS_NODEV | MS_NOSUID;
    if (read_only) {
        remount_flags |= MS_RDONLY;
    }
    if (::mount(nullptr, dst.c_str(), nullptr, remount_flags, nullptr) != 0) {
        return false;
    }
    return true;
}

bool FilesystemManager::create_minimal_dev() {
    std::string dev_dir = config_.sandbox_root_dir + "/dev";
    make_dir_p(dev_dir);

    // Mount tmpfs on /dev
    ::mount("tmpfs", dev_dir.c_str(), "tmpfs", MS_NOSUID | MS_NOEXEC, "mode=0755,size=4m");

    // Bind mount essential host devices
    const std::vector<std::string> dev_nodes = {"/dev/null", "/dev/zero", "/dev/urandom", "/dev/full"};
    for (const auto& node : dev_nodes) {
        std::string target = config_.sandbox_root_dir + node;
        int fd = ::open(target.c_str(), O_CREAT | O_WRONLY | O_CLOEXEC, 0666);
        if (fd >= 0) ::close(fd);
        ::mount(node.c_str(), target.c_str(), nullptr, MS_BIND, nullptr);
    }
    return true;
}

bool FilesystemManager::setup_mounts() {
    const std::string& root = config_.sandbox_root_dir;
    make_dir_p(root);

    // Read-only system paths
    safe_bind_mount("/usr", root + "/usr", true);

    // Isolated /etc: never expose host credentials (/etc/shadow, /etc/sudoers)
    std::string etc_dir = root + "/etc";
    make_dir_p(etc_dir);
    ::mount("tmpfs", etc_dir.c_str(), "tmpfs", MS_NODEV | MS_NOSUID, "size=8m,mode=0755");

    safe_bind_mount("/etc/ld.so.cache", etc_dir + "/ld.so.cache", true);
    safe_bind_mount("/etc/alternatives", etc_dir + "/alternatives", true);
    safe_bind_mount("/etc/ssl", etc_dir + "/ssl", true);
    safe_bind_mount("/etc/resolv.conf", etc_dir + "/resolv.conf", true);
    safe_bind_mount("/etc/localtime", etc_dir + "/localtime", true);

    {
        std::ofstream p(etc_dir + "/passwd");
        if (p.is_open()) {
            p << "root:x:0:0:root:/tmp:/bin/sh\nrunbox:x:1000:1000:Runbox:/workspace:/bin/sh\n";
        }
        std::ofstream g(etc_dir + "/group");
        if (g.is_open()) {
            g << "root:x:0:\nrunbox:x:1000:\n";
        }
    }

    // UsrMerge symlinks
    auto safe_symlink = [](const char* target, const std::string& linkpath) {
        ::unlink(linkpath.c_str());
        if (::symlink(target, linkpath.c_str()) != 0) {
            // Symlink exists or handled
        }
    };

    safe_symlink("usr/bin", root + "/bin");
    safe_symlink("usr/lib", root + "/lib");
    safe_symlink("usr/lib64", root + "/lib64");
    safe_symlink("usr/sbin", root + "/sbin");

    // Writable /tmp (tmpfs with bounded memory and inode limits)
    if (config_.mount_tmp) {
        std::string tmp_dir = root + "/tmp";
        make_dir_p(tmp_dir);
        ::mount("tmpfs", tmp_dir.c_str(), "tmpfs", MS_NODEV | MS_NOSUID, "size=64m,nr_inodes=10000,mode=1777");
    }

    // Writable workspace
    std::string ws_dir = root + "/workspace";
    make_dir_p(ws_dir);
    if (!config_.host_workspace_dir.empty()) {
        make_dir_p(config_.host_workspace_dir);
        safe_bind_mount(config_.host_workspace_dir, ws_dir, false);
    } else {
        ::mount("tmpfs", ws_dir.c_str(), "tmpfs", MS_NODEV | MS_NOSUID, "size=64m,nr_inodes=10000,mode=0755");
    }

#ifdef RUNBOX_ENABLE_COVERAGE
    // During test coverage runs, bind mount repo root so libgcov can record child coverage
    safe_bind_mount("/mnt/d/MERN/Runbox", root + "/mnt/d/MERN/Runbox", false);
#endif

    // Minimal /dev
    if (config_.mount_dev) {
        create_minimal_dev();
    }

    // Private /proc
    if (config_.mount_proc) {
        std::string proc_dir = root + "/proc";
        make_dir_p(proc_dir);
        ::mount("proc", proc_dir.c_str(), "proc", MS_NODEV | MS_NOSUID | MS_NOEXEC, nullptr);
    }

    return true;
}

bool FilesystemManager::setup_sandbox_filesystem() {
    if (!setup_mounts()) {
        return false;
    }

    // Enter chroot
    if (::chroot(config_.sandbox_root_dir.c_str()) != 0) {
        return false;
    }

    if (::chdir("/workspace") != 0) {
        if (::chdir("/") != 0) {
            // fallback
        }
    }

    return true;
}

bool FilesystemManager::apply_landlock_rules() {
    if (!config_.enable_landlock) return true;

    // Check if Landlock is supported
    long abi = ::syscall(SYS_landlock_create_ruleset, nullptr, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi <= 0) {
        return true;
    }

    uint64_t all_access = LANDLOCK_ACCESS_FS_EXECUTE |
                          LANDLOCK_ACCESS_FS_WRITE_FILE |
                          LANDLOCK_ACCESS_FS_READ_FILE |
                          LANDLOCK_ACCESS_FS_READ_DIR |
                          LANDLOCK_ACCESS_FS_REMOVE_DIR |
                          LANDLOCK_ACCESS_FS_REMOVE_FILE |
                          LANDLOCK_ACCESS_FS_MAKE_DIR |
                          LANDLOCK_ACCESS_FS_MAKE_REG |
                          LANDLOCK_ACCESS_FS_MAKE_SYM |
                          LANDLOCK_ACCESS_FS_TRUNCATE;

    struct landlock_ruleset_attr ruleset_attr = {};
    ruleset_attr.handled_access_fs = all_access;

    int ruleset_fd = static_cast<int>(::syscall(SYS_landlock_create_ruleset, &ruleset_attr, sizeof(ruleset_attr), 0));
    if (ruleset_fd < 0) {
        return true;
    }

    auto add_path_rule = [ruleset_fd](const char* path, uint64_t access) {
        int fd = ::open(path, O_PATH | O_CLOEXEC);
        if (fd < 0) return;

        struct landlock_path_beneath_attr path_beneath = {};
        path_beneath.allowed_access = access;
        path_beneath.parent_fd = fd;

        ::syscall(SYS_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &path_beneath, 0);
        ::close(fd);
    };

    // Read + Execute only on system directories
    uint64_t ro_exec = LANDLOCK_ACCESS_FS_READ_FILE |
                       LANDLOCK_ACCESS_FS_READ_DIR |
                       LANDLOCK_ACCESS_FS_EXECUTE;

    add_path_rule("/usr", ro_exec);
    add_path_rule("/lib", ro_exec);
    add_path_rule("/lib64", ro_exec);
    add_path_rule("/bin", ro_exec);
    add_path_rule("/etc", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR);
    add_path_rule("/dev", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE);
    add_path_rule("/proc", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR);

    // Full access on /workspace and /tmp
    add_path_rule("/workspace", all_access);
    add_path_rule("/tmp", all_access);

#ifdef RUNBOX_ENABLE_COVERAGE
    add_path_rule("/mnt/d/MERN/Runbox", all_access);
#endif

    // Restrict self
    ::prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
    ::syscall(SYS_landlock_restrict_self, ruleset_fd, 0);
    ::close(ruleset_fd);

    return true;
}

bool FilesystemManager::teardown_sandbox() {
    return true;
}

} // namespace runbox::filesystem
