# Runbox Security Model & Attack Surface Analysis

## 1. Threat Model & Adversarial Assumptions

Runbox operates under an adversarial threat model: **Any submitted source code is treated as malicious and active exploit payload until proven otherwise.**

The system defends against:
1. **Arbitrary Code Execution on Host:** Untrusted code attempting to break out of process boundaries and modify host files, binaries, or services.
2. **Host Filesystem Snooping:** Attempts to read `/etc/shadow`, `/etc/sudoers`, SSH private keys, environment files, or other tenants' execution workspaces.
3. **Denial of Service (DoS) & Resource Starvation:**
   - CPU hogging (infinite loops, busy spins).
   - Memory exhaustion (rapid heap allocations, memory leaks, fork-based RAM fills).
   - Process bombs (fork bombs, thread exhaustion, infinite background daemons).
   - Disk saturation (filling `/tmp` or workspace with gigabytes of data).
4. **Network Intrusion & Exfiltration:**
   - Opening outbound TCP/UDP sockets to C2 servers.
   - Probing local host services (`127.0.0.1:8000`, cloud metadata services `169.254.169.254`).
   - Listening on host interfaces.
5. **Privilege Escalation:**
   - Executing `setuid`/`setgid` binaries to regain root on the host.
   - Abusing capabilities (e.g. `CAP_SYS_ADMIN`, `CAP_NET_RAW`, `CAP_SYS_PTRACE`).
   - SUID manipulation or modifying inner user namespace state.
6. **Cross-Tenant Interference:**
   - Inspecting or interfering with other concurrently running jobs in memory or disk.
   - Ptrace snooping across namespaces.

---

## 2. Multi-Layer Defense Matrix

| Attack Vector | Primary Defensive Layer | Secondary Defensive Layer | Kernel / System Mechanism |
| :--- | :--- | :--- | :--- |
| **Host Filesystem Reading** | Private chroot & Landlock LSM | Mount Namespace (`MS_PRIVATE`) | Read-only `/usr`, synthetic tmpfs `/etc`, path-beneath enforcement |
| **Host Filesystem Modification** | Read-only bind-mounts | Landlock write bans | `MS_RDONLY` remount on system paths, Landlock access masks |
| **Fork Bomb / Process Saturation** | Cgroup v2 `pids.max` | PID Namespace isolation | Kernel task counter enforcing process cap |
| **Memory Exhaustion (OOM)** | Cgroup v2 `memory.max` | `memory.oom.group = 1` | Immediate group-wide OOM kill by Linux kernel |
| **Disk Paging Abuse** | Cgroup v2 `memory.swap.max = 0` | Writable tmpfs caps | Swap allocation completely forbidden |
| **CPU Starvation** | Cgroup v2 `cpu.max` bandwidth quota | Monotonic clock timeout monitor | CFS scheduler quota throttling & supervisor SIGKILL |
| **Network Exfiltration / Infiltration** | Network Namespace (`CLONE_NEWNET`) | Seccomp syscall filter | Zero network interfaces, socket calls return `EPERM` |
| **Privilege Escalation** | `PR_SET_NO_NEW_PRIVS` | Capability dropping (`CAPBSET_DROP`) | Ambient and bounding capability sets cleared (0..63) |
| **Container Escape / Syscall Abuse** | Seccomp-BPF filter | Unprivileged User Namespace | `SECCOMP_RET_ERRNO(EPERM)` default action, explicit kill list |
| **Host Process Snooping** | PID Namespace (`CLONE_NEWPID`) | Private `/proc` mount | Sandbox PID 1 visibility only, host processes invisible |
| **Cross-Tenant Snooping** | Ephemeral per-execution workspaces | `0700` filesystem permissions | Cryptographic unique IDs (`job-<uuid>`), auto-cleanup |
| **Host Environment Leakage** | Complete environment sanitization | Hardcoded safe environment | Host environment variables stripped before `execve` |

---

## 3. Seccomp-BPF Syscall Filter Details

Runbox implements a default-deny architecture. Any syscall not explicitly whitelisted is intercepted and rejected with `EPERM` (Operation not permitted).

### 3.1 Prohibited Hostile Syscalls (Immediate SIGSYS / Kill)
The following dangerous syscalls are explicitly banned:
- `reboot`, `kexec_load`, `kexec_file_load`
- `init_module`, `finit_module`, `delete_module`
- `ptrace`, `process_vm_readv`, `process_vm_writev`
- `bpf`, `userfaultfd`
- `swapon`, `swapoff`
- `settimeofday`, `clock_settime`, `adjtimex`
- `acct`, `iopl`, `ioperm`

### 3.2 Permitted System Calls (Categorized by Need)
1. **Memory Management:** `brk`, `mmap`, `mprotect`, `munmap`, `mremap`, `madvise`.
2. **File & Stream I/O:** `read`, `write`, `readv`, `writev`, `pread64`, `pwrite64`, `close`, `lseek`, `dup`, `dup2`, `dup3`, `fcntl`, `ioctl`, `statx`, `fstat`, `newfstatat`, `openat`, `openat2`.
3. **Process Metadata & Synchronization:** `getpid`, `getppid`, `gettid`, `getuid`, `geteuid`, `getgid`, `getegid`, `futex`, `clone`, `clone3`, `set_robust_list`, `get_robust_list`, `set_tid_address`, `rseq`.
4. **Time & Clocks:** `clock_gettime`, `clock_getres`, `clock_nanosleep`, `nanosleep`, `gettimeofday`.
5. **Execution Lifecycle:** `exit`, `exit_group`, `execve`, `execveat`, `wait4`, `waitid`, `restart_syscall`.
6. **Compiler Toolchain (CppCompilation only):** `fork`, `vfork`, `pipe`, `pipe2`, `utimensat`, `umask`, `chmod`, `fchmod`, `fchmodat`, `getrlimit`.

---

## 4. Verification and Empirical Testing

All 40 security controls have been validated against an automated adversarial test suite (`tests/adversarial/test_adversarial_suite.py`):
1. **Infinite CPU loop** (`test_01`) -> Terminated by `SIGKILL` at monotonic timeout deadline.
2. **Memory allocation bomb** (`test_02`) -> Cgroup v2 `memory.max` OOM killer terminates process immediately.
3. **Process creation bomb / Fork bomb** (`test_03`) -> Process spawning blocked at `pids.max` boundary.
4. **Host filesystem access** (`test_04`) -> Access to `/etc/shadow` denied via VFS mount isolation and Landlock.
5. **Unauthorized host write** (`test_05`) -> Read-only bind mount rejects write with `EROFS`.
6. **Path traversal** (`test_06`) -> Directory traversal `../../../../root` trapped inside chroot / Landlock boundary.
7. **Symlink escape attempt** (`test_07`) -> Symlink resolution remains bounded inside private mount.
8. **Network connection attempt** (`test_08`) -> Outbound socket connection to `8.8.8.8:80` blocked by `CLONE_NEWNET`.
9. **Excessive stdout flooding** (`test_09`) -> Output clamped at configured `output_limit_bytes` without pipe buffer deadlocks.
10. **Excessive stderr flooding** (`test_10`) -> Output clamped at configured `output_limit_bytes`.
11. **Infinite child process** (`test_11`) -> Cgroup supervisor kills all descendant PIDs upon job termination.
12. **Background daemon persistence** (`test_12`) -> Fork with detached `setsid` session terminated via `cgroup.kill`.
13. **Large temporary file creation** (`test_13`) -> Bounded tmpfs size (64MB) rejects write with `ENOSPC`.
14. **Excessive thread creation** (`test_14`) -> Spawning 1000 Python OS threads bounded by `pids.max`.
15. **Runtime timeout enforcement** (`test_15`) -> Monotonic timer triggers `SIGKILL` at exact deadline via `signalfd`.
16. **Host environment leakage** (`test_16`) -> Host environment stripped; child receives sanitized environment.
17. **Fork and parent exit** (`test_17`) -> Orphaned child reparented to PID 1 inside namespace and reaped.
18. **File descriptor exhaustion** (`test_18`) -> Opening 100,000 files blocked at `max_fds` (`EMFILE`).
19. **IPC namespace isolation** (`test_19`) -> Host POSIX / SysV shared memory blocked by `CLONE_NEWIPC`.
20. **UTS hostname isolation** (`test_20`) -> Hostname modification isolated to `CLONE_NEWUTS`.
21. **Process group signal isolation** (`test_21`) -> `kill(-1, SIGTERM)` blocked from affecting host processes.
22. **`/dev/shm` exhaustion** (`test_22`) -> Shared memory isolated inside private mount namespace.
23. **Null byte binary injection** (`test_23`) -> Malicious binary strings rejected by API validation schema.
24. **Cgroup & workspace cleanup** (`test_24`) -> Subtree directories and temporary workspaces completely unlinked.
25. **Double-fork daemon escape** (`test_25`) -> All descendants tracked in `cgroup.procs` and terminated.
26. **Tmpfs inode exhaustion** (`test_26`) -> Creating 50,000 empty files blocked by `nr_inodes=10000` limit.
27. **Mmap virtual memory storm** (`test_27`) -> Massive sparse mmap allocations managed without physical RAM starvation.
28. **Raw IPv6 socket creation** (`test_28`) -> Rejected with `EPERM` (no `CAP_NET_RAW`, network NS down).
29. **Unix domain socket host escape** (`test_29`) -> Host sockets (`/var/run/docker.sock`) inaccessible inside chroot.
30. **Host `/proc/environ` leakage** (`test_30`) -> Masked private `/proc` shows only container PID 1.
31. **Sysfs tampering attempt** (`test_31`) -> Writing to `/sys/kernel/...` blocked by read-only / unmounted sysfs.
32. **Device node creation (`mknod`)** (`test_32`) -> Blocked by Landlock and capability drop (`EPERM`).
33. **Ptrace syscall blocked** (`test_33`) -> Ptrace attach immediately terminated with `SIGSYS` via Seccomp filter.
34. **eBPF `bpf()` syscall blocked** (`test_34`) -> Invoking `bpf()` terminated with `SIGSYS` via Seccomp filter.
35. **Reboot syscall blocked** (`test_35`) -> Invoking `reboot()` terminated with `SIGSYS` via Seccomp filter.
36. **Mount syscall blocked** (`test_36`) -> Calling `mount()` terminated with `SIGSYS` via Seccomp filter.
37. **Setuid capability escalation** (`test_37`) -> Forbidden by `PR_SET_NO_NEW_PRIVS` and unprivileged map.
38. **SIGKILL mask attempt** (`test_38`) -> Kernel guarantees `SIGKILL` cannot be caught or ignored.
39. **CPU starvation spinning cores** (`test_39`) -> Parallel spinning threads throttled by Cgroup v2 `cpu.max`.
40. **Multi-tenant quota isolation** (`test_40`) -> Tenant burst concurrency isolated; noisy neighbors rate-limited.

---

## 5. Control Plane Authentication & Multi-Tenancy

1. **Timing-Safe Authentication:**
   - API tokens are validated via SHA-256 digest comparison using `secrets.compare_digest()`, reducing side-channel timing attack risks during token comparison. (Whole-request timing may still show minor network/ASGI jitter).
   - Authentication credentials can be supplied via `Authorization: Bearer <token>` or `X-API-Key: <token>`.
2. **Anti-Enumeration Resource Scoping:**
   - Any query or cancellation attempt against an execution ID belonging to a different tenant returns HTTP 404 Not Found, completely concealing execution ID existence.
3. **Sliding-Window Rate Limiting:**
   - Per-tenant submission frequency is bounded via in-memory sliding windows. Excessive requests return HTTP 429 Too Many Requests with a dynamic `Retry-After` header.
4. **Concurrency Quota Enforcement:**
   - Each tenant has an independent concurrent execution cap (`TENANT_MAX_CONCURRENT_JOBS`), preventing any single tenant from starving the worker pool.
5. **Supervisor Boundary Validation:**
   - The standalone `runbox-supervisor` binary validates all `JobConfig` inputs before creating execution namespaces. Traversal sequences, null bytes, non-alphanumeric execution IDs, and unwhitelisted executable paths are rejected prior to container initialization.
