# Runbox v0.1.1 — Supervisor Boundary & IPC Protocol

## 1. Overview

The Runbox Supervisor (`core/supervisor/`) is an unprivileged Linux process responsible for constructing the isolated execution jail, applying kernel-enforced sandboxing constraints, monitoring workload telemetry, enforcing monotonic timeouts, and performing atomic cleanup upon completion.

The boundary between the untrusted Python control plane and the C++20 supervisor binary is defined by an auditable, typed JSON IPC contract with strict compile-time and runtime validation.

---

## 2. IPC Protocol Specification

### 2.1 Configuration Schema (`JobConfig`)
The supervisor is invoked via CLI arguments:
```bash
/path/to/runbox-supervisor --config /path/to/workspace/config.json
```

The payload adheres to the following typed schema:
```json
{
  "execution_id": "job-a1b2c3d4e5f6",
  "language": "python",
  "executable_path": "/usr/bin/python3",
  "argv": ["-u", "main.py"],
  "workspace_dir": "/tmp/runbox_ws_job-a1b2c3d4e5f6",
  "stdin": "optional_stdin_data",
  "limits": {
    "timeout_ms": 3000,
    "memory_mb": 128,
    "cpu_quota_percent": 50,
    "process_limit": 32,
    "output_limit_bytes": 1048576
  }
}
```

### 2.2 Validation Invariants (`JobConfig::validate`)
Prior to invoking any system calls or unsharing namespaces, `JobConfig::validate()` enforces strict security invariants:
1. **Execution ID Format**:
   - Length between 1 and 64 characters.
   - Character whitelist: `[a-zA-Z0-9_-]`. Any characters such as `;`, `/`, `&`, `|`, `$` trigger immediate rejection.
2. **Language Support**:
   - Must be one of: `"python"`, `"python3"`, `"cpp"`, `"cpp_compile"`, `"minimal"`.
3. **Executable Path Whitelist**:
   - Must be an absolute path starting with `/`.
   - Traversal pattern `..` is strictly prohibited.
   - Binary must reside under an approved system directory (`/usr/bin/`, `/bin/`, `/workspace/`, `/sandbox/workspace/`) or match the job's dedicated `workspace_dir`.
4. **Workspace Path**:
   - Must be absolute with no `..` path traversal components.
5. **Resource Limits Bounds**:
   - `timeout_ms`: `[10, 60000]`
   - `memory_mb`: `[16, 2048]`
   - `cpu_quota_percent`: `[1, 100]`
   - `process_limit`: `[1, 128]`
   - `output_limit_bytes`: `[1024, 10485760]`

---

## 3. Synchronization & Execution Lifecycle

```
[Parent: Supervisor]                             [Child: Intermediate]              [Grandchild: Workload]
        |                                                  |                                  |
   1. Initialize Cgroup v2                                 |                                  |
   2. fork() --------------------------------------------> |                                  |
        |                                            3. unshare() (PID, NET, NS, ...)         |
   4. Read sync_c2p pipe <------------------------ 3. Write ready byte                        |
   5. Add PID to cgroup.procs                              |                                  |
   6. Write UID/GID maps (/proc/PID/uid_map)               |                                  |
   7. Write sync_p2c pipe -----------------------> 8. Read go byte                            |
        |                                            9. Setup Private Mounts                  |
        |                                           10. Setup Filesystem & Landlock           |
        |                                           11. Drop Capabilities & PR_SET_NO_NEW_PRIVS|
        |                                           12. Install Seccomp BPF Filter            |
        |                                           13. dup2() I/O descriptors                |
        |                                           14. fork() -----------------------------> |
        |                                                  |                         15. execve() (PID 1)
        |                                           16. waitpid(workload_pid) <------- Workload runs
        |                                                  |                                  |
   17. Non-blocking monitor loop (waitpid WNOHANG)         |                                  |
   18. Monotonic timeout check                             |                                  |
   19. Stream consumer drains stdout/stderr pipes          |                                  |
        |                                                  |                         20. Workload exits
        |                                           21. waitpid returns                       |
        | <----------------------------------------- 22. Intermediate _exit(status)
   23. cgroup.collect_usage()
   24. cgroup.terminate_all() via cgroup.kill
   25. cgroup.destroy()
   26. Emit JSON ExecutionResult to stdout
```

### 3.1 Pipe Deadlock Prevention
All standard streams (`stdin`, `stdout`, `stderr`) are handled via non-blocking pipes managed by `runbox::monitoring::StreamConsumer`. Output is consumed concurrently in a background thread with an upper bound cap (`limits.output_limit_bytes`), preventing processes from hanging on pipe buffer backpressure.

### 3.2 Monotonic Clock Timing
Timeouts are governed by `CLOCK_MONOTONIC` (`runbox::process::get_monotonic_time_ms()`), ensuring that adjustments to wall-clock time (NTP steps, leap seconds) cannot affect timeout precision.
