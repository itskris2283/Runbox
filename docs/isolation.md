# Runbox Isolation Mechanics & Kernel Primitives

## 1. Linux Kernel Namespaces

Namespaces partition global system resources into isolated instances. Inside a namespace, a process has an independent view of system facilities without visibility into or interference from other namespaces.

### 1.1 PID Namespace (`CLONE_NEWPID`)
- **Process ID Virtualization:** Inside the namespace, process IDs start at 1. Host PIDs are completely hidden.
- **PID 1 Semantics:** The first child spawned inside the namespace becomes PID 1.
  - Signal Forwarding: Unhandled signals sent to PID 1 that have no handler installed are discarded (except SIGKILL/SIGSTOP from ancestor namespaces).
  - Orphan Reaping: When a child process terminates before its descendants, the descendants are reparented to PID 1 inside the namespace, not to host systemd/init.
  - Clean Teardown: If PID 1 terminates, the kernel destroys the PID namespace and issues SIGKILL to every remaining process in that namespace.

### 1.2 User Namespace (`CLONE_NEWUSER`)
- **Unprivileged Operation:** Allows Runbox to establish isolated containers without requiring `setuid` root helper binaries or root privileges on the host.
- **UID/GID Mapping Protocol:**
  1. The child calls `unshare(CLONE_NEWUSER | ...)`.
  2. The child signals the parent via `sync_c2p` pipe.
  3. The parent opens `/proc/<child_pid>/setgroups` and writes `deny`.
  4. The parent opens `/proc/<child_pid>/gid_map` and maps inside GID 0 to host outside GID.
  5. The parent opens `/proc/<child_pid>/uid_map` and maps inside UID 0 to host outside UID.
  6. The parent releases the child via `sync_p2c` pipe.
  7. Now inside the user namespace, the child has `CAP_SYS_ADMIN` capability *strictly scoped to its private user namespace*, allowing mount setup and chroot. Outside the user namespace, the process possesses zero privileges.

### 1.3 Mount Namespace (`CLONE_NEWNS`)
- **Propagation Control:** Marks all mounts `MS_REC | MS_PRIVATE`.
- **Mount Shadowing:** Creates ephemeral in-memory filesystems (`tmpfs`) that exist only for the duration of the execution lifecycle.

### 1.4 Network Namespace (`CLONE_NEWNET`)
- **Complete Isolation:** Spawns with zero network devices.
- **Attack Prevention:** Disallows loopback sockets, Unix domain sockets outside the container, and raw packet interfaces.

### 1.5 IPC Namespace (`CLONE_NEWIPC`)
- Isolates System V IPC objects (semaphores, message queues, shared memory segments) and POSIX message queues.
- Prevents cross-process memory inspection or signaling via IPC identifiers.

### 1.6 UTS Namespace (`CLONE_NEWUTS`)
- Virtualizes hostname and NIS domain.
- Set to `runbox-<execution_id_prefix>`. Prevents disclosure of host hostname.

---

## 2. Filesystem Layout & Sandbox Root

Runbox creates an ephemeral sandbox root directory at `/tmp/runbox_sb_<execution_id>` before entering `chroot`:

```
/tmp/runbox_sb_<execution_id>/
├── bin -> usr/bin          (UsrMerge symlink)
├── lib -> usr/lib          (UsrMerge symlink)
├── lib64 -> usr/lib64      (UsrMerge symlink)
├── sbin -> usr/sbin        (UsrMerge symlink)
├── usr/                    (Bind-mount of host /usr, MS_RDONLY)
├── etc/                    (8MB tmpfs, isolated)
│   ├── ld.so.cache         (Bind-mount of host loader cache)
│   ├── alternatives/       (Bind-mount of system alternatives)
│   ├── ssl/                (Bind-mount of CA certificates)
│   ├── resolv.conf         (Bind-mount of dummy resolv.conf)
│   ├── localtime           (Bind-mount of host timezone)
│   ├── passwd              (Synthetic: root:x:0:0:root:/tmp:/bin/sh)
│   └── group               (Synthetic: root:x:0:)
├── dev/                    (4MB tmpfs)
│   ├── null                (Bind-mount of host /dev/null)
│   ├── zero                (Bind-mount of host /dev/zero)
│   ├── urandom             (Bind-mount of host /dev/urandom)
│   └── full                (Bind-mount of host /dev/full)
├── proc/                   (Fresh private procfs mount)
├── tmp/                    (64MB tmpfs, mode=1777)
└── workspace/              (Ephemeral execution directory, writable)
    ├── source code         (main.py / main.cpp)
    └── binary              (main)
```

---

## 3. Cgroups v2 Resource Accounting

Runbox leverages the unified Linux cgroups v2 hierarchy (`/sys/fs/cgroup/runbox`):

### 3.1 Subtree Control Delegation
Before child cgroups can configure resource caps, the parent hierarchy must enable controllers:
```bash
echo "+memory +cpu +pids" > /sys/fs/cgroup/runbox/cgroup.subtree_control
```

### 3.2 Ephemeral Execution Cgroups
Each execution job is assigned a unique directory:
```bash
/sys/fs/cgroup/runbox/<execution_id>/
├── cgroup.procs            # PIDs assigned to this sandbox
├── memory.max              # Hard memory limit in bytes
├── memory.swap.max         # Set to 0 to forbid swap paging
├── memory.oom.group        # Set to 1 for atomic group kill on OOM
├── memory.peak             # High watermark memory telemetry
├── cpu.max                 # Bandwidth quota: "<quota_us> <period_us>"
├── cpu.stat                # Telemetry: usage_usec, user_usec, system_usec
├── pids.max                # Maximum concurrent tasks/threads
├── pids.peak               # High watermark task telemetry
├── pids.events             # max event counter tracking fork bomb throttling
└── cgroup.kill             # Atomic termination trigger
```
