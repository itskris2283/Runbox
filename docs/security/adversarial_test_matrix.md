# Runbox v0.1.1 — Adversarial Attack Verification Matrix

## 1. Overview
The Runbox adversarial test suite (`tests/adversarial/test_adversarial_suite.py`) subjects the sandboxing infrastructure to 40 distinct adversarial attack vectors. All vectors execute against a running Runbox instance on Ubuntu 24.04 LTS.

---

## 2. Attack Vectors & Security Assertions

| # | Attack Vector Name | Threat Category | Attack Description | Expected Sandbox Defense |
|---|---|---|---|---|
| 1 | `test_01_infinite_cpu_loop` | Denial of Service | Unbounded `while True` loop | Terminated by `SIGKILL` at monotonic timeout deadline |
| 2 | `test_02_memory_exhaustion` | Resource Exhaustion | 200MB allocation with 32MB limit | OOM killer terminates process via `memory.max` |
| 3 | `test_03_process_creation_bomb` | DoS / Fork Bomb | Rapid `os.fork()` recursion | Process spawning blocked at `pids.max` boundary |
| 4 | `test_04_host_filesystem_access` | Information Disclosure | Attempt to open and read `/etc/shadow` | Blocked via VFS mount isolation and Landlock (EACCES/ENOENT) |
| 5 | `test_05_unauthorized_file_writes`| Host Tampering | Attempt to write to `/etc/hacked.txt` | Read-only bind mount rejects write with EROFS |
| 6 | `test_06_path_traversal` | Container Escape | Directory traversal `../../../../../root` | Chroot jail and Landlock prevent escape past root |
| 7 | `test_07_symlink_escape_attempts`| Container Escape | Creation of symlink to `/etc` or `/proc` | Relative resolution remains bounded inside private mount |
| 8 | `test_08_network_connection_attempts` | Exfiltration | Outbound socket connection to 8.8.8.8:80 | Blocked by `CLONE_NEWNET` (Network unreachable) |
| 9 | `test_09_excessive_stdout` | Resource Exhaustion | Writing >10MB of data to stdout | Output truncated at configured `output_limit_bytes` |
| 10| `test_10_excessive_stderr` | Resource Exhaustion | Writing >10MB of data to stderr | Output truncated at configured `output_limit_bytes` |
| 11| `test_11_infinite_child_process` | Orphan Persistence | Workload forks infinite sleeper and exits | Cgroup supervisor kills all descendant PIDs |
| 12| `test_12_background_process_persistence`| DoS / Leaks | Fork with detached setsid session | `cgroup.kill` terminates entire process hierarchy |
| 13| `test_13_large_temporary_file_creation`| Disk Exhaustion | Writing 500MB file to `/tmp` | Bounded tmpfs size (64MB) rejects write with ENOSPC |
| 14| `test_14_excessive_thread_creation` | DoS | Spawning 1000 Python OS threads | Bounded by `pids.max` (threads count against PID limit) |
| 15| `test_15_runtime_timeout` | DoS | Sleep exceeding job timeout | Monotonic timer triggers SIGKILL at deadline |
| 16| `test_16_host_environment_variables` | Credential Leak | Inspecting `os.environ` for secrets | Sanitized environment contains only whitelisted vars |
| 17| `test_17_fork_and_parent_exit` | Zombie Escape | Parent exits immediately leaving orphan | Reparented to PID 1 inside namespace and reaped |
| 18| `test_18_file_descriptor_exhaustion` | DoS | Opening 100,000 files in a loop | Blocked at `max_fds` (EMFILE) |
| 19| `test_19_ipc_namespace_isolation` | Lateral Movement | Accessing host POSIX / SysV shared memory | Blocked by `CLONE_NEWIPC` |
| 20| `test_20_uts_hostname_isolation` | Spoofing | Altering hostname via `sethostname` | Isolated to `CLONE_NEWUTS` or blocked by seccomp |
| 21| `test_21_process_group_signal_isolation`| Lateral Movement | `kill(-1, SIGTERM)` | Blocked from affecting host or adjacent containers |
| 22| `test_22_dev_shm_exhaustion` | Memory DoS | Flooding `/dev/shm` | Isolated or unmounted; host memory protected |
| 23| `test_23_null_byte_binary_injection` | Input Tampering | Injecting null bytes into source code | Rejected by API validation schema |
| 24| `test_24_cgroup_cleanup_verification` | Resource Leak | Verifying cgroup directories after job | Cgroup directory cleanly unlinked via `rmdir` |
| 25| `test_25_double_fork_daemon_escape` | Process Escape | Double-fork daemonization pattern | All descendants tracked in `cgroup.procs` and killed |
| 26| `test_26_tmpfs_inode_exhaustion` | Filesystem DoS | Creating 50,000 empty files in `/tmp` | Blocked by `nr_inodes=10000` tmpfs limit |
| 27| `test_27_mmap_virtual_memory_storm` | Memory DoS | Attempting massive sparse mmap allocations | Virtual address space managed without starving physical RAM |
| 28| `test_28_raw_ipv6_socket_creation` | Network Escape | Opening `AF_INET6` raw socket | Rejected with EPERM (no `CAP_NET_RAW`, network NS down) |
| 29| `test_29_unix_domain_socket_host_escape`| Container Escape | Connecting to `/var/run/docker.sock` | Path does not exist in chroot/mount namespace |
| 30| `test_30_host_proc_environ_leakage`| Credential Leak | Reading `/proc/1/environ` | Masked private `/proc` shows only container PID 1 |
| 31| `test_31_sys_fs_modification_attempt`| Kernel Tampering | Writing to `/sys/kernel/...` | `/sys` unmounted or mounted strictly read-only |
| 32| `test_32_mknod_device_creation` | Device Node Escape | Attempting `mknod` for block/char device | Blocked by Landlock and capability drop (EPERM) |
| 33| `test_33_ptrace_syscall_blocked` | Privilege Escalation | Attempting `ptrace` attach to PID 1 | Immediately terminated with `SIGSYS` via Seccomp filter |
| 34| `test_34_ebpf_bpf_syscall_blocked` | Kernel Exploitation | Invoking `bpf()` syscall | Immediately terminated with `SIGSYS` via Seccomp filter |
| 35| `test_35_reboot_shutdown_syscall_blocked`| Host DoS | Invoking `reboot()` syscall | Immediately terminated with `SIGSYS` via Seccomp filter |
| 36| `test_36_mount_syscall_blocked` | Filesystem Escape | Invoking `mount()` syscall inside container| Terminated with `SIGSYS` via Seccomp filter |
| 37| `test_37_setuid_capability_escalation`| Privilege Escalation | Attempting `setuid(0)` or capset | Forbidden by `PR_SET_NO_NEW_PRIVS` and unprivileged map |
| 38| `test_38_sigkill_mask_attempt` | Immortality Attack | Attempting to mask or trap `SIGKILL` | Kernel guarantees `SIGKILL` cannot be caught or ignored |
| 39| `test_39_cpu_starvation_spinning_cores`| Core Starvation | 4 parallel threads spinning 100% CPU | Throttled by Cgroup v2 `cpu.max` quota |
| 40| `test_40_multi_tenant_quota_isolation`| Noisy Neighbor | Tenant A bursts 10 jobs to exhaust workers | Tenant B job executes without starvation; Tenant A rate-limited |

---

## 3. Results Summary
- Total attack vectors evaluated: **40**
- Passing / mitigated: **40 (100%)**
- Host breaches detected: **0**
- Resource leakage across boundaries: **0**
