# Runbox v0.1.1 — Privilege Reduction & Capability Model

## 1. Threat Definition & Principles

The Runbox execution environment is designed under the principle of **Least Privilege and Defense in Depth**. Untrusted code submitted by external users must never inherit administrative capabilities, access the host network, tamper with system mounts, or inspect host secrets.

Every execution runs with unprivileged user namespace mapping, stripped capability sets, mandatory `PR_SET_NO_NEW_PRIVS`, and cleared supplementary groups.

---

## 2. Kernel Isolation Layers

### 2.1 Linux Namespaces (`core/namespaces/namespaces.cpp`)
Prior to entering the workload container, the child process unshares six orthogonal namespace boundaries:
- `CLONE_NEWUSER`: Creates an independent user namespace. The supervisor writes `/proc/[pid]/uid_map` mapping the host unprivileged user to UID 0 inside the container, granting the container process authority over its own namespace without granting elevated permissions on the host.
- `CLONE_NEWPID`: Provides an isolated PID space. The workload binary executes as PID 1 within its namespace.
- `CLONE_NEWNET`: Disables network access. The isolated namespace has only a loopback interface (`lo`) in the `DOWN` state.
- `CLONE_NEWNS`: Establishes private mount propagation (`MS_REC | MS_PRIVATE`).
- `CLONE_NEWIPC`: Isolates System V IPC and POSIX message queues.
- `CLONE_NEWUTS`: Isolates host and domain names, preventing hostname spoofing.

### 2.2 Privilege Reduction (`core/security/privileges.cpp`)
Privilege dropping is implemented in strict order:
1. **PR_SET_NO_NEW_PRIVS**:
   - `prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)` is invoked before any execve or filter installation.
   - Prevents setuid/setgid binaries or filesystem capability attributes from elevating privileges during execution.
2. **Capability Dropping**:
   - Ambient capabilities cleared via `prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0)`.
   - All 64 capability bits in the bounding set (`CAP_SYS_ADMIN`, `CAP_NET_RAW`, `CAP_SYS_PTRACE`, `CAP_DAC_OVERRIDE`, etc.) are dropped via `prctl(PR_CAPBSET_DROP, cap, 0, 0, 0)`.
3. **Supplementary Groups Dropping**:
   - `setgroups(0, nullptr)` is invoked to ensure no inherited supplementary group permissions persist into the sandbox.
4. **Identity Dropping**:
   - Real, effective, and saved UIDs and GIDs transition to unprivileged values (`setresgid`, `setresuid`).
5. **Privilege Verification**:
   - `PrivilegeManager::verify_privileges_dropped()` validates that effective UID/GID match target unprivileged identities and that `PR_GET_NO_NEW_PRIVS` is asserted.

### 2.3 Resource Limits (RLIMITS)
As a secondary barrier supporting Cgroups v2:
- `RLIMIT_CORE = 0`: Disables core dumps to prevent dumping sensitive runtime memory onto disk upon SIGSEGV/SIGABRT.
- `RLIMIT_CPU`: Enforces fallback CPU termination via `SIGXCPU` if supervisor monitoring stalls.
- `RLIMIT_FSIZE`: Restricts individual file creation size.
- `RLIMIT_NOFILE`: Binds maximum open file descriptors.

---

## 3. Mandatory Access Control (MAC) & Landlock LSM

Where supported by the host Linux kernel (Linux 5.13+), Runbox enforces Landlock LSM rulesets (`core/filesystem/filesystem_isolation.cpp`):
- Read-only execution paths: `/usr`, `/lib`, `/lib64`, `/bin`.
- Read-only metadata: `/etc`.
- Read/write access: Scoped strictly to the ephemeral `/workspace`, `/tmp`, and `/dev` pseudofiles.
- All other host filesystem hierarchies are completely inaccessible at the kernel VFS layer.
