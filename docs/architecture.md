# Runbox Architecture & System Specification

## 1. Executive Overview

Runbox is a high-security Linux code execution engine and sandboxing infrastructure engineered to execute untrusted user code under strict, verifiable resource, privilege, and filesystem boundaries.

Unlike simple Docker wrappers or online compilers using `subprocess.Popen` without kernel isolation, Runbox enforces process isolation, Linux namespaces, unified cgroups v2 resource accounting, Seccomp-BPF system-call filters, Landlock LSM filesystem sandboxing, and monotonic deadline monitoring.

```
                          +------------------------------------------+
                          |   FastAPI REST API / Web Dashboard       |
                          |      (Unprivileged Host Control Plane)   |
                          +--------------------+---------------------+
                                               |
                                     Async Job Dispatch
                                               |
                                               v
                          +------------------------------------------+
                          |      Asyncio Scheduler & Worker Pool     |
                          |        (Concurrency Limit: 10)           |
                          +--------------------+---------------------+
                                               |
                                    Invokes via Arguments
                                               |
                                               v
                          +------------------------------------------+
                          |       runbox-supervisor (C++20)          |
                          |    (Parent Coordinator & Synchronizer)   |
                          +--------------------+---------------------+
                                               |
                     1. Cgroups v2 Assignment  | 2. UID/GID Mapping (User NS)
                                               v
                          +------------------------------------------+
                          |           Intermediate Child             |
                          |       (Unshares Namespaces & Mounts)     |
                          +--------------------+---------------------+
                                               |
                                    Forks Inner Workload
                                               |
                                               v
                          +------------------------------------------+
                          |         Workload Container (PID 1)       |
                          |   - Seccomp-BPF System Call Filter       |
                          |   - Landlock LSM Sandboxed FS            |
                          |   - Dropped Capabilities & No-New-Privs  |
                          |   - Writable Ephemeral /workspace & /tmp |
                          |   - /usr Read-Only, Isolated /etc tmpfs  |
                          |   - Python 3.12 / GCC 13 C++20 Workload  |
                          +------------------------------------------+
```

---

## 2. Core Architectural Subsystems

### 2.1 C++ Sandbox Supervisor (`core/supervisor/`)
The supervisor binary (`runbox-supervisor`) serves as the security boundary coordinator.
- **Input:** Strongly-typed execution configuration (`JobConfig`) supplied via JSON file or CLI flags. Enforces strict schema validation (`JobConfig::validate`) at `main.cpp` before namespace creation, rejecting non-alphanumeric execution IDs, directory traversal sequences, out-of-range bounds, and unwhitelisted binaries.
- **Coordination:** Creates dedicated pipes for stdin, stdout, stderr, and bidirectional synchronization (`sync_c2p`, `sync_p2c`).
- **Resource Limits:** Provisions an ephemeral child cgroup directory under `/sys/fs/cgroup/runbox/<execution_id>` before releasing the workload.
- **Telemetry & Monitoring:** Employs Linux `signalfd` for zero-delay child exit notifications combined with monotonic deadline clocks (`CLOCK_MONOTONIC`), eliminating busy sleep latency and reducing timeout jitter to 3.0 – 6.0 ms. Collects kernel CPU time (`cpu.stat`), peak physical memory (`memory.peak`), and peak task count (`pids.peak`).
- **Reaping & Teardown:** Terminates all processes in the execution cgroup (`cgroup.kill` or group SIGKILL), drains pipe buffers asynchronously, removes the cgroup directory, and deletes temporary sandbox root mounts. In the async Python runtime invoker, the supervisor process is strictly awaited (`await proc.wait()`) prior to workspace directory removal, preventing file handle leaks and orphaned directories.

### 2.2 Linux Namespaces (`core/namespaces/`)
Runbox isolates the execution environment using 6 distinct Linux namespaces:
1. **User Namespace (`CLONE_NEWUSER`):** Enables unprivileged containerization without requiring `setuid` binaries or root host privileges. Inside the user namespace, the child is mapped as UID 0 to permit private mount operations (`mount`, `pivot_root`/`chroot`). Outside the namespace, the process retains zero host privileges.
2. **PID Namespace (`CLONE_NEWPID`):** Ensures processes cannot observe or signal host processes. The workload process is spawned as PID 1 inside the isolated namespace. When PID 1 terminates, all child or daemon descendants are automatically reaped.
3. **Mount Namespace (`CLONE_NEWNS`):** Creates an independent mount table marked `MS_REC | MS_PRIVATE`. Host mounts do not propagate into the sandbox, and sandbox mounts do not leak to the host.
4. **Network Namespace (`CLONE_NEWNET`):** Disconnects all network interfaces. The sandbox has zero network devices (no Ethernet, no Wi-Fi, and no loopback `lo` by default). Any socket binding, packet transmission, or network access immediately fails with `ENETUNREACH` or `EPERM`.
5. **IPC Namespace (`CLONE_NEWIPC`):** Isolates System V IPC and POSIX message queues.
6. **UTS Namespace (`CLONE_NEWUTS`):** Isolates hostname and NIS domain name to prevent hostname snooping.

### 2.3 Unified Cgroups v2 Manager (`core/cgroups/`)
All resource constraints are enforced using the unified cgroup v2 hierarchy at `/sys/fs/cgroup/runbox`:
- `memory.max`: Hard resident memory limit.
- `memory.swap.max`: Set to 0 to completely disallow disk paging and swap abuse.
- `memory.oom.group`: Set to 1. If any process in the sandbox triggers an OOM event, the entire execution group is terminated simultaneously by the kernel to prevent orphaned zombies.
- `cpu.max`: Enforces hard bandwidth quota throttling (e.g. `100000 100000` for 100% quota, `50000 100000` for 50%).
- `pids.max`: Limits maximum concurrent tasks (threads and processes) within the sandbox to prevent fork bombs.
- `cgroup.kill`: Atomic kernel mechanism to terminate all members of a cgroup in a single system operation.

### 2.4 Filesystem Isolation & Landlock LSM (`core/filesystem/`)
The sandbox filesystem is structured using a private chroot and Landlock LSM:
- **Two-Step Recursive Bind Mounts:** In accordance with Linux VFS user-namespace invariants, system directories (`/usr`) are mounted via an initial recursive bind (`MS_BIND | MS_REC`), followed by a strict remount (`MS_BIND | MS_REC | MS_REMOUNT | MS_NODEV | MS_NOSUID | MS_RDONLY`). This prevents `EINVAL` kernel rejection while enforcing immutable read-only constraints.
- `/bin`, `/lib`, `/lib64`, `/sbin`: UsrMerge symlinks into `usr/bin`, `usr/lib`, etc.
- `/etc`: Private 8MB tmpfs with synthetic dummy `passwd` and `group` files. Host credentials (`/etc/shadow`, `/etc/sudoers`, SSH keys) are completely inaccessible.
- `/dev`: Minimal 4MB tmpfs containing only bind-mounted `/dev/null`, `/dev/zero`, `/dev/urandom`, and `/dev/full`.
- `/proc`: Freshly mounted private proc filesystem reflecting only sandbox PID 1 and its descendants.
- `/tmp`: Private 64MB tmpfs bounded by explicit size (`size=64m`) and inode caps (`nr_inodes=10000`, `mode=1777`), preventing both storage and inode exhaustion attacks.
- `/workspace`: Dedicated bind-mounted workspace directory containing user source code and compiled binaries.
- **Landlock LSM:** Implements kernel path-beneath restrictions ensuring the sandbox process cannot access any path outside `/usr`, `/etc`, `/tmp`, `/dev`, and `/workspace`.

### 2.5 Seccomp-BPF Syscall Filter (`core/seccomp/`)
A custom Berkeley Packet Filter profile is compiled and loaded via `libseccomp`:
- Default action: `SECCOMP_RET_ERRNO(EPERM)`.
- Explicit kill list: `reboot`, `kexec_load`, `ptrace`, `bpf`, `init_module`, `finit_module`, `delete_module`, `swapon`, `swapoff`, `settimeofday`, `clock_settime`.
- Specialised profiles:
  - `Minimal`: Standard execution of pre-compiled or static tools.
  - `PythonExecution`: Permits interpreter runtime operations while denying network, socket, raw hardware, and process snooping.
  - `CppCompilation`: Allows toolchain driver operations (`fork`, `vfork`, `pipe`, `wait4`, `umask`, `chmod`, `getrlimit`) strictly required by GCC/Clang while preventing host escapes.
  - `CppExecution`: Restricts user C++ binaries to bounded file I/O, memory allocations, and CPU computation.

### 2.6 Privilege Management (`core/security/`)
- `PR_SET_NO_NEW_PRIVS`: Prevents any binary or child process from acquiring elevated privileges via setuid/setgid bits.
- **POSIX Capabilities:** Completely drops all ambient and bounding capabilities from `cap=0` to `cap=63`.
- **Resource Limits (rlimits):** Sets `RLIMIT_CORE = 0` (preventing sensitive memory dumps), `RLIMIT_CPU` soft/hard limits, `RLIMIT_FSIZE` file creation caps, and `RLIMIT_NOFILE` descriptor caps.
- **Sanitized Environment:** Strips all host environment variables, providing only minimal safe entries (`PATH=/usr/local/bin:/usr/bin:/bin`, `LANG=C.UTF-8`, `TMPDIR=/tmp`, `PYTHONUNBUFFERED=1`).

---

## 3. Execution Lifecycle State Machine

```
   [Submitted] ---> [Queued in Memory] ---> [Assigned Worker Slot]
                                                    |
                                                    v
                                       [Workspace Directory Created]
                                                    |
                                                    v
                                    [Cgroup v2 Provisioned (/sys/fs/...)]
                                                    |
                                                    v
                                  [fork() Child Process in Supervisor]
                                                    |
                                  Child Calls unshare(NEWNS|NEWPID|NEWUSER...)
                                                    |
                          +-------------------------+-------------------------+
                          |                                                   |
                   Child writes 1 to sync_c2p                         Parent receives sync_c2p
                          |                                                   |
                   Child blocks on sync_p2c                           Parent writes cgroup.procs
                          |                                           Parent writes uid_map / gid_map
                          |                                           Parent writes 1 to sync_p2c
                          |                                                   |
                          v                                                   v
                   Child unblocks                                     Parent starts StreamConsumer
                          |                                           (Consuming stdout/stderr pipes)
                   Child mounts /usr (ro),                                    |
                   Mounts isolated /etc (tmpfs),                              |
                   Mounts /dev, /proc, /tmp, /workspace                       |
                          |                                                   |
                   Child enters chroot & chdir("/workspace")                  |
                   Child applies Landlock ruleset                             |
                   Child drops capabilities & enables no_new_privs            |
                   Child installs Seccomp-BPF filter                          |
                          |                                                   |
                   Child forks PID 1 workload                                 |
                          |                                                   |
                   Workload calls execve()                                    |
                          |                                                   v
                          +---------------------------------------> Parent monitors deadline
                                                                    & cgroup metrics
                                                                              |
                                     +----------------------------------------+
                                     |
                                     v
                        [Workload Terminates or Times Out]
                                     |
                                     v
                        [cgroup.kill / SIGKILL Reaping]
                                     |
                                     v
                        [Telemetry & Exit Status Recorded]
                                     |
                                     v
                        [Temporary Workspace & Cgroup Cleaned]
                                     |
                                     v
                             [Result Persisted]
```
