#include "core/seccomp/seccomp_rules.hpp"

#include <seccomp.h>
#include <sys/prctl.h>
#include <iostream>
#include <vector>

namespace runbox::seccomp {

SeccompFilter::SeccompFilter(SeccompProfile profile)
    : profile_(profile) {}

bool SeccompFilter::install() {
    // PR_SET_NO_NEW_PRIVS is mandatory before installing seccomp filters as an unprivileged process
    if (::prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        std::cerr << "[runbox::seccomp] prctl(PR_SET_NO_NEW_PRIVS) failed\n";
        return false;
    }

    return build_and_load_filter();
}

bool SeccompFilter::build_and_load_filter() {
    // Default action: fail closed with EPERM error
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ERRNO(EPERM));
    if (ctx == nullptr) {
        std::cerr << "[runbox::seccomp] seccomp_init failed\n";
        return false;
    }

    // Helper lambda to add rules
    auto allow = [ctx](int syscall_nr) {
        return seccomp_rule_add(ctx, SCMP_ACT_ALLOW, syscall_nr, 0) == 0;
    };

    auto kill = [ctx](int syscall_nr) {
        return seccomp_rule_add(ctx, SCMP_ACT_KILL_PROCESS, syscall_nr, 0) == 0;
    };

    // 1. Explicitly terminate on dangerous privilege escalation / host escape attempts
    const std::vector<int> hostile_syscalls = {
        SCMP_SYS(ptrace),
        SCMP_SYS(bpf),
        SCMP_SYS(kexec_load),
        SCMP_SYS(kexec_file_load),
        SCMP_SYS(reboot),
        SCMP_SYS(mount),
        SCMP_SYS(umount2),
        SCMP_SYS(pivot_root),
        SCMP_SYS(setns),
        SCMP_SYS(unshare),
        SCMP_SYS(chroot),
        SCMP_SYS(init_module),
        SCMP_SYS(finit_module),
        SCMP_SYS(delete_module),
        SCMP_SYS(iopl),
        SCMP_SYS(ioperm),
        SCMP_SYS(lookup_dcookie),
        SCMP_SYS(perf_event_open),
    };

    for (int sys : hostile_syscalls) {
        kill(sys);
    }

    // 2. Base permitted syscalls (Memory, I/O, Signals, Process metadata, Time, Dynamic Linking)
    const std::vector<int> base_allowed = {
        SCMP_SYS(read), SCMP_SYS(write), SCMP_SYS(readv), SCMP_SYS(writev),
        SCMP_SYS(pread64), SCMP_SYS(pwrite64),
        SCMP_SYS(close), SCMP_SYS(fstat), SCMP_SYS(newfstatat), SCMP_SYS(lseek),
        SCMP_SYS(dup), SCMP_SYS(dup2), SCMP_SYS(dup3), SCMP_SYS(fcntl), SCMP_SYS(ioctl),
        SCMP_SYS(flock), SCMP_SYS(ftruncate), SCMP_SYS(umask),
        SCMP_SYS(pipe), SCMP_SYS(pipe2),
        SCMP_SYS(openat), SCMP_SYS(openat2), SCMP_SYS(statx),
        SCMP_SYS(brk), SCMP_SYS(mmap), SCMP_SYS(munmap), SCMP_SYS(mprotect),
        SCMP_SYS(madvise), SCMP_SYS(mremap),
        SCMP_SYS(rt_sigaction), SCMP_SYS(rt_sigprocmask), SCMP_SYS(rt_sigreturn),
        SCMP_SYS(sigaltstack),
        SCMP_SYS(getpid), SCMP_SYS(getppid), SCMP_SYS(gettid),
        SCMP_SYS(getuid), SCMP_SYS(geteuid), SCMP_SYS(getgid), SCMP_SYS(getegid),
        SCMP_SYS(uname), SCMP_SYS(sysinfo),
        SCMP_SYS(clock_gettime), SCMP_SYS(clock_getres), SCMP_SYS(clock_nanosleep),
        SCMP_SYS(nanosleep), SCMP_SYS(gettimeofday),
        SCMP_SYS(poll), SCMP_SYS(ppoll), SCMP_SYS(select), SCMP_SYS(pselect6),
        SCMP_SYS(epoll_create1), SCMP_SYS(epoll_ctl), SCMP_SYS(epoll_wait), SCMP_SYS(epoll_pwait),
        SCMP_SYS(futex), SCMP_SYS(clone), SCMP_SYS(clone3),
        SCMP_SYS(set_robust_list), SCMP_SYS(get_robust_list),
        SCMP_SYS(set_tid_address), SCMP_SYS(rseq),
        SCMP_SYS(prctl), SCMP_SYS(arch_prctl),
        SCMP_SYS(getdents64), SCMP_SYS(access), SCMP_SYS(faccessat), SCMP_SYS(faccessat2),
        SCMP_SYS(readlink), SCMP_SYS(readlinkat), SCMP_SYS(getcwd),
        SCMP_SYS(getrandom),
        SCMP_SYS(exit), SCMP_SYS(exit_group),
        SCMP_SYS(execve), SCMP_SYS(execveat),
        SCMP_SYS(wait4), SCMP_SYS(waitid),
        SCMP_SYS(restart_syscall)
    };

    for (int sys : base_allowed) {
        allow(sys);
    }

    // 3. Runtime Profile Specifics
    if (profile_ == SeccompProfile::PythonExecution ||
        profile_ == SeccompProfile::CppCompilation ||
        profile_ == SeccompProfile::CppExecution) {

        const std::vector<int> runtime_allowed = {
            SCMP_SYS(unlink), SCMP_SYS(unlinkat),
            SCMP_SYS(mkdir), SCMP_SYS(mkdirat),
            SCMP_SYS(rmdir),
            SCMP_SYS(rename), SCMP_SYS(renameat), SCMP_SYS(renameat2),
            SCMP_SYS(sched_yield),
            SCMP_SYS(sched_getaffinity),
            SCMP_SYS(getrusage),
            SCMP_SYS(prlimit64),
            SCMP_SYS(tgkill)
        };
        for (int sys : runtime_allowed) {
            allow(sys);
        }
    }

    if (profile_ == SeccompProfile::CppCompilation) {
        // Compiler processes need fork, vfork, wait4, waitid, umask, chmod
        const std::vector<int> compiler_allowed = {
            SCMP_SYS(fork),
            SCMP_SYS(wait4), SCMP_SYS(waitid),
            SCMP_SYS(vfork),
            SCMP_SYS(utimensat),
            SCMP_SYS(umask),
            SCMP_SYS(chmod), SCMP_SYS(fchmod), SCMP_SYS(fchmodat),
            SCMP_SYS(getrlimit)
        };
        for (int sys : compiler_allowed) {
            allow(sys);
        }
    }

    // Load filter into kernel
    int rc = seccomp_load(ctx);
    seccomp_release(ctx);

    if (rc != 0) {
        std::cerr << "[runbox::seccomp] seccomp_load failed: rc=" << rc << "\n";
        return false;
    }

    return true;
}

} // namespace runbox::seccomp
