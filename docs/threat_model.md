# Runbox Threat Model & Security Architecture

**Document Version:** 1.0.0  
**Target Release:** Runbox v0.1.0 / v1.0.0  
**Status:** Living Specification  
**Classification:** Engineering Security Specification  

---

## 1. Executive Summary & Objective

Runbox is a secure multi-tenant code execution engine designed to run untrusted, potentially malicious user-submitted programs (in Python, C++, and future runtimes) on Linux infrastructure. The core objective is executing arbitrary user computation under deterministic, independently verified boundary constraints without permitting compromise of host assets, disruption of co-tenant executions, or denial of host service.

This threat model defines:
1. Protected assets and operational trust boundaries.
2. Threat actors, attacker profiles, and attack vectors.
3. Defense-in-depth isolation layers and mitigation strategies.
4. Residual risks, explicit non-goals, and security limitations.

---

## 2. Protected Assets

The Runbox isolation boundary is engineered to protect eight critical asset categories:

1. **Host Operating System & Filesystem:** Host configuration files (`/etc`, `/boot`, `/sys`), kernel parameters, host binaries, libraries, user home directories, and system logs.
2. **Host Processes & Execution Tree:** Unrelated host services (systemd, sshd, container runtimes, API web servers) and supervisor parent processes.
3. **Host Credentials & Secrets:** API tokens, cloud instance metadata credentials (`169.254.169.254`), SSH private keys, environment variables of parent processes, database connection credentials.
4. **Co-Tenant Executions (Cross-Execution Isolation):** Memory, file workspaces, intermediate compiler outputs, pipes, and process trees belonging to other concurrent or sequential execution jobs.
5. **System Hardware Resources (CPU, Memory, Disk, PIDs):** Prevention of host starvation via runaway memory allocation (OOM), infinite CPU loops, fork bombs, disk quota exhaustion, or file descriptor depletion.
6. **Network & Peripheral Interfaces:** Host network adapters, loopback interfaces, local sockets (UNIX domain sockets), hardware devices (`/dev/mem`, `/dev/kmem`, raw disk blocks).
7. **Control Plane & Application Configuration:** FastAPI application server state, job scheduler internal queue, persistence database (`runbox.db`), and administrator-defined system limits.
8. **Execution Audit & Metadata Integrity:** Prevention of tampering, falsification, or suppression of execution logs, exit codes, resource statistics, and security violation alerts.

---

## 3. Trust Boundaries & Architectural Zones

```
+-----------------------------------------------------------------------------------+
| ZONE 0: UNTRUSTED / EXTERNAL                                                      |
|   Client HTTP Submissions (JSON Source Code, Stdin, Resource Limit Overrides)     |
+-----------------------------------------------------------------------------------+
                                      |
                     [TLS / HTTP / Schema Validation]
                                      v
+-----------------------------------------------------------------------------------+
| ZONE 1: UNPRIVILEGED CONTROL PLANE (Runbox API & Scheduler)                       |
|   - FastAPI Unprivileged Process (UID 1000+)                                      |
|   - Hard limits enforcement (Clamps user limits to system max)                    |
|   - SQLite metadata persistence (WAL mode)                                        |
|   - Task worker pool / Bounded execution queue                                    |
+-----------------------------------------------------------------------------------+
                                      |
                    [Direct execve with typed JSON config]
                                      v
+-----------------------------------------------------------------------------------+
| ZONE 2: SUPERVISOR LAYER (runbox-supervisor)                                      |
|   - Standalone C++20 process per execution                                        |
|   - Allocates dedicated Cgroup v2 subtree                                         |
|   - Synchronizes child creation via bidirectional pipes                           |
|   - Enforces timeouts using CLOCK_MONOTONIC                                       |
|   - Captures & truncates stdout/stderr via non-blocking bounded buffers           |
|   - Performs atomic subtree termination (cgroup.kill)                             |
+-----------------------------------------------------------------------------------+
                                      |
       [Fork/Clone + Unshare + Mounts + Pivot_Root + Landlock + Drops + Seccomp]
                                      v
+-----------------------------------------------------------------------------------+
| ZONE 3: CONTAINED EXECUTION ENVIRONMENT (Sandbox Child)                           |
|   - Linux Namespaces: PID, Mount, Network, User, IPC, UTS                         |
|   - Cgroups v2: memory.max, cpu.max, pids.max, memory.oom.group=1                 |
|   - Filesystem: Private mount, read-only system binds, tmpfs /tmp, Landlock ABI   |
|   - Privileges: PR_SET_NO_NEW_PRIVS, Cap drops (empty caps), non-root UID         |
|   - Syscall Filter: Runtime-specific Seccomp BPF (EPERM / KILL_PROCESS)           |
|   - Rlimits: RLIMIT_CPU, RLIMIT_AS, RLIMIT_FSIZE, RLIMIT_NPROC, RLIMIT_NOFILE     |
|   - Untrusted Code: Python Interpreter / Compiled C++ Binary                      |
+-----------------------------------------------------------------------------------+
```

---

## 4. Threat Actors & Attacker Capabilities

We model the attacker as an arbitrary remote actor submitting code to the Runbox execution API. The attacker has:
- Complete control over submitted source code (Python, C++).
- Full control over input stdin data.
- Ability to submit arbitrary compiler directives, preprocessor macros, assembly (`__asm__`), and native binary calls.
- Motivation to escape the sandbox, read host secrets, consume infinite resources, attack local network services, or interfere with other executions.

We assume the attacker **does NOT have**:
- Physical hardware access.
- Valid root credentials on the host OS.
- Pre-existing shell access to the host or API server.

---

## 5. Threat Scenarios & Mitigations Matrix

| # | Threat Scenario | Attack Vector | Runbox Mitigation Layer | Residual Risk & Observation |
|---|---|---|---|---|
| **1** | **Infinite CPU Exhaustion** | `while True: pass` or C++ `for(;;)` | `cgroups v2 cpu.max` quota throttling + `CLOCK_MONOTONIC` supervisor wall-clock timeout + `RLIMIT_CPU`. | Attacker cannot consume more than allotted CPU quota; terminated at deadline. |
| **2** | **Memory Exhaustion (OOM)** | Large allocation arrays / memory bombs | `cgroups v2 memory.max`, `memory.swap.max=0`, `memory.oom.group=1`, and `RLIMIT_AS`. | Kernel OOM killer terminates entire sandbox process group. Logged via `memory.events`. |
| **3** | **Process / Fork Bomb** | `:(){ :\|:& };:` or recursive `os.fork()` | `cgroups v2 pids.max` (e.g., 32) + `RLIMIT_NPROC` + PID namespace PID 1 cleanup. | Fork attempts fail with `EAGAIN` once `pids.max` is reached. Host cannot be starved. |
| **4** | **Host Filesystem Snooping** | Attempting to read `/etc/shadow`, `/root`, host `/proc` | Mount namespace + `pivot_root` / read-only bind mounts + Landlock LSM + unprivileged user mapping. | Host paths simply do not exist in the mount namespace. Landlock denies path resolution. |
| **5** | **Arbitrary File Modification** | Attempting to overwrite system binaries or other jobs | Root filesystem is mounted `MS_RDONLY, MS_NODEV, MS_NOSUID`. Only `/workspace` and `/tmp` are writable tmpfs. | Write attempts fail with `EROFS` or `EACCES`. |
| **6** | **Directory Traversal / Symlinks** | Symlinks pointing to `../../../../etc` | Mount isolation prevents seeing parent trees. Safe open operations, Landlock path scoping. | Symlink resolution terminates within the mount namespace; escape is impossible. |
| **7** | **Network Probing / Exfiltration** | Sockets to host LAN, cloud metadata `169.254.169.254` | Network namespace (`CLONE_NEWNET`) with no default gateway or veth pair + Seccomp socket filtering. | Network stack has only loopback interface `lo` down. `connect()` fails immediately with `ENETUNREACH` or `EPERM`. |
| **8** | **Output Stream Flooding** | Infinite `print("A" * 1000000)` | Bounded supervisor pipes with `max_output_bytes` threshold (default 1MB). Stream truncation flag. | Output is capped at threshold; supervisor stops reading or truncates stream. Server memory safe. |
| **9** | **Background Child Persistence** | Spawning daemon process (`setsid`, double-fork) | PID namespace (when PID 1 dies, all descendants receive SIGKILL) + `cgroup.kill` atomic cleanup. | No background processes can survive supervisor teardown. |
| **10** | **Privilege Escalation** | `setuid` binaries, capability manipulation | `PR_SET_NO_NEW_PRIVS` set before execve. All POSIX capabilities cleared. `nosuid` on all mounts. | Kernel prevents regaining privileges or gaining capabilities across execve. |
| **11** | **Hostile Kernel Exploits** | Invoking obscure kernel syscalls | Strict Seccomp-BPF whitelist per runtime (`python`, `cpp_compile`, `cpp_run`). | Syscalls outside profile return `SECCOMP_RET_ERRNO(EPERM)` or trigger `SECCOMP_RET_KILL_PROCESS`. Prohibited calls (`ptrace`, `bpf`, `reboot`, `mount`) trigger instant termination. |
| **12** | **Cross-Job Interference** | One execution reading/writing another's workspace | Every execution receives a UUID, a dedicated tmpfs workspace, and a private cgroup. | Workspaces are mutually invisible across mount namespaces. Anti-enumeration returns HTTP 404 on both cross-tenant status inspection and cancellation attempts. |
| **13** | **API Resource / Argument Injection** | Sending malicious command line flags or limits | Strict Pydantic model validation. Clamped limits. Command arguments are passed as fixed `char* const[]` array to `execve()`, never via shell. | Shell injection is impossible by architecture. Typed validation enforces path whitelists. |
| **14** | **API Timing / Token Snooping** | Timing attacks against API authentication tokens | SHA-256 token verification using `secrets.compare_digest()` constant-time comparison. | Reduces side-channel timing-attack risk during token comparison; does not eliminate macro-level HTTP request jitter. |
| **15** | **Noisy Neighbor Starvation** | Flooding API with rapid concurrent requests | Sliding-window per-tenant rate limiting + per-tenant concurrency quotas. | Requests exceeding rate return HTTP 429; concurrent slots clamped per tenant. |
| **16** | **Tmpfs Inode Depletion** | Creating thousands of zero-byte files in `/tmp` | Tmpfs mount options specify explicit `nr_inodes=10000` bounds alongside `size=64m`. | Filesystem rejects file creation with `ENOSPC` when inode ceiling is reached. |
| **17** | **Process Detachment / Daemonization** | Double-forking into new session (`setsid`) | All child tasks captured into cgroup v2 controller; atomic `cgroup.kill` issued upon teardown. | Zero survivor processes, verified by cgroup task counter telemetry. |

---

## 6. Explicit Security Limitations & Non-Goals

1. **Shared-Kernel Isolation Reality:**
   Runbox uses native Linux kernel mechanisms (namespaces, cgroups, seccomp, Landlock). While these provide robust operating-system level sandboxing, they share the host kernel. Runbox does not guarantee protection against undiscovered zero-day Linux kernel privilege escalation vulnerabilities.
2. **Microarchitectural Side Channels:**
   Spectre, Meltdown, MDS, and related hardware cache/timing side-channel attacks are outside the scope of OS-level namespace sandboxing. Full mitigation requires hypervisor-level isolation (e.g., AWS Firecracker microVMs) or dedicated physical cores.
3. **Denial of Service via Kernel Bug:**
   A program that triggers a kernel panic or deadlock via a kernel bug cannot be isolated by userspace mechanisms.
4. **Future MicroVM Roadmap:**
   For multi-tenant public environments with untrusted adversarial workloads, Runbox includes architectural hooks to delegate execution to a Firecracker microVM backend in future releases.
