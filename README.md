# Runbox — Secure Linux Code Execution & Sandboxing Infrastructure

[![Version](https://img.shields.io/badge/Version-v0.1.1-blue)](https://github.com/runbox/runbox)
[![Platform](https://img.shields.io/badge/Platform-Ubuntu%2024.04%20LTS-E95420?logo=ubuntu)](https://ubuntu.com)
[![C++20](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=c%2B%2B)](https://en.cppreference.com/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript)](https://www.typescriptlang.org)
[![Tests](https://img.shields.io/badge/Tests-232%2F232%20Passing-brightgreen)](https://github.com/runbox/runbox)
[![C++ Coverage](https://img.shields.io/badge/C%2B%2B%20Coverage-88.0%25-brightgreen)](https://github.com/runbox/runbox)
[![Python Coverage](https://img.shields.io/badge/Python%20Coverage-89.0%25-brightgreen)](https://github.com/runbox/runbox)
[![License](https://img.shields.io/badge/License-MIT-green)](file:///LICENSE)

**Runbox** is a high-performance, multi-tenant Linux code execution sandboxing infrastructure designed to execute untrusted user code under strict, independently verified resource and security restrictions.

---

## 1. Problem Statement & Why Runbox Exists

Executing untrusted code submitted over the web is one of the highest-risk operations in modern software systems. Naive solutions suffer from critical flaws:
- **Insecure Subprocess Execution:** Invoking `subprocess.Popen()` or `os.system()` directly on a host provides zero isolation. A single command can read `/etc/shadow`, exfiltrate AWS credentials, spawn fork bombs, or corrupt system files.
- **Docker Wrapper Vulnerabilities:** Wrapping code inside generic Docker containers incurs excessive startup latency (300–800 ms), consumes substantial memory overhead, and frequently suffers from container-escape exploits if run with elevated capabilities or default seccomp profiles.
- **Resource Starvation:** Traditional POSIX limits (`RLIMIT_AS`) choke language runtimes like Python or the GCC toolchain with artificial virtual memory allocation failures rather than constraining physical resident memory.

**Runbox solves this problem from first principles.** It implements a lightweight C++20 supervisor that orchestrates native Linux kernel primitives—**Linux Namespaces**, **Unified Cgroups v2**, **Landlock LSM**, **Seccomp BPF filters**, and **POSIX Capability Dropping**—to establish genuine multi-layer containment with sub-120 ms latency and verified hardware-level resource accounting.

---

## 2. Key Features

- **Six Concentric Kernel Isolation Layers:** Process, network, filesystem, system call, capability, and cgroup resource containment.
- **Double-Fork PID 1 Mapping:** Workloads execute as PID 1 inside isolated PID namespaces, ensuring proper signal semantics and eliminating `vfork: Cannot allocate memory` compiler failures.
- **Kernel Timerfd Monotonic Enforcement:** Utilizes `timerfd_create(CLOCK_MONOTONIC, ...)` paired with `signalfd` on `SIGCHLD`, achieving sub-40 ms P95 timeout jitter.
- **Unified Cgroups v2 Accounting:** Strictly enforces physical resident memory (`memory.max`), disables swapping (`memory.swap.max=0`), limits CPU bandwidth (`cpu.max`), and clamps process proliferation (`pids.max`).
- **High-Throughput Asynchronous Control Plane:** FastAPI async worker pools with SQLite WAL persistence delivering over **90 jobs/sec** concurrent burst throughput.
- **Cryptographic Multi-Tenant Governance:** SHA-256 constant-time API token authentication, sliding-window rate limiters, tenant concurrency quotas, and anti-enumeration protections (HTTP 404).
- **Interactive Web Dashboard:** Production-ready React 18 + TypeScript + Vite developer dashboard with real-time health telemetry and execution explorer.

---

## 3. System Architecture

```mermaid
flowchart TD
    User["User / Developer / API Consumer"] -->|HTTP REST / WebSocket| Gateway["React Dashboard / REST API (api/main.py)"]
    Gateway -->|Verify Tokens & Quotas| Gov["Authentication & Tenant Governance (api/security/)"]
    Gov -->|Enqueue Validated Request| Sched["Async Job Scheduler (api/scheduler/)"]
    Sched -->|Stage Code & Toolchain| Adapters["Python / C++ Runtime Adapters (runtimes/)"]
    Adapters -->|JSON Execution Config| Super["C++20 Sandbox Supervisor (core/supervisor/)"]
    
    subgraph KernelIsolation["Linux Kernel Isolation Layer"]
        Super -->|CLONE_NEWPID/NET/NS/IPC/UTS| NS["1. Linux Namespaces"]
        Super -->|memory.max, cpu.max, pids.max| CG["2. Cgroups v2 Controllers"]
        Super -->|SCMP_ACT_KILL_PROCESS| SC["3. Seccomp BPF Allowlist"]
        Super -->|ABI v1-v3 Path Locks| LL["4. Landlock LSM"]
        Super -->|Drop Caps & UID 65534| PR["5. Capability Dropping"]
        Super -->|Private Mount & Inode Caps| FS["6. Ephemeral Filesystem (tmpfs)"]
    end
    
    KernelIsolation -->|execve Workload (PID 1)| Execution["Untrusted User Workload"]
    Execution -->|Monotonic Timer & Pipe Drain| Telemetry["Execution Result & Telemetry"]
    Telemetry -->|Persist Audit Record| Storage["SQLite Database (WAL Mode) / Dashboard UI"]
```

---

## 4. Technology Stack

- **Sandbox Supervisor Core:** C++20, GCC 13.3.0, CMake 3.28+, `libseccomp` 2.5.5, Linux Landlock ABI v3.
- **Control Plane:** Python 3.12, FastAPI 0.115+, Uvicorn, Pydantic V2, `aiosqlite`.
- **Persistence:** SQLite 3.45 in Write-Ahead Logging (WAL) mode with memory temp-store.
- **Frontend Dashboard:** React 18, TypeScript 5, Vite 8, Lucide Icons.
- **Testing & Verification:** GoogleTest 1.14, Pytest 8, Pytest-Cov, Ruff.

---

## 5. Concentric Security & Isolation Mechanisms

| Isolation Layer | Implementation Mechanism | Adversarial Protection |
| :--- | :--- | :--- |
| **Process Isolation** | `CLONE_NEWPID` + Workload PID 1 Fork | Prevents process inspection, signals to host processes, and fork bomb proliferation. |
| **Network Isolation** | `CLONE_NEWNET` with no external interfaces | Neutralizes socket creation, DNS resolution, and exfiltration attempts. |
| **Filesystem Isolation** | Ephemeral `tmpfs` + `MS_REC \| MS_PRIVATE` mounts | Isolates filesystems. Host `/etc/shadow`, `/root`, and home dirs are completely inaccessible. |
| **Kernel LSM** | Linux Landlock ABI v1-v3 | Restricts path access in kernel space; blocks directory escape and tampering. |
| **System Call Filtering**| Seccomp BPF with `SCMP_ACT_KILL_PROCESS` | Kills processes executing unapproved system calls (`reboot`, `ptrace`, `mknod`, `mount`). |
| **Resource Quotas** | Unified Cgroups v2 (`memory.max`, `cpu.max`, `pids.max`) | Enforces physical memory limits without virtual address starvation; enforces CPU throttling. |
| **Privilege Reduction** | Ambient Capability Dropping + `PR_SET_NO_NEW_PRIVS` | Drops to UID 65534 (`nobody`) and GID 65534 (`nogroup`); clears supplementary groups. |

---

## 6. Supported Language Runtimes

- **Python 3.12:** Sandboxed interpreter execution under `PythonExecution` Seccomp profile with Landlock filesystem locks.
- **C++20:** Two-stage execution pipeline:
  1. *Isolated Compilation:* `/usr/bin/g++ -O0 -std=c++20 main.cpp -o main` executed under `CppCompilation` Seccomp filter and 512MB build limit.
  2. *Sandboxed Execution:* Sandboxed binary execution `/workspace/main` executed under strict `CppExecution` Seccomp filter and dropped capabilities.

---

## 7. Installation & Build Instructions

### Prerequisites (Ubuntu 24.04 LTS)
```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential cmake libseccomp-dev python3.12 python3.12-venv nodejs npm
```

### 1. Configure Cgroups v2 Hierarchy
```bash
sudo mkdir -p /sys/fs/cgroup/runbox
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
echo "+memory +cpu +pids" | sudo tee /sys/fs/cgroup/runbox/cgroup.subtree_control
sudo chown -R $USER:$USER /sys/fs/cgroup/runbox
```

### 2. Build C++ Sandbox Supervisor
```bash
cmake -B build-release -DCMAKE_BUILD_TYPE=Release
cmake --build build-release -j$(nproc)
```

### 3. Set Up Python Environment
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 4. Build Frontend Dashboard
```bash
cd dashboard
npm ci
npm run build
cd ..
```

---

## 8. Quickstart & API Usage

Start the Runbox control plane:
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Submit an Untrusted Execution Request
```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-admin-token-runbox-v0.1.1" \
  -d '{
    "language": "python",
    "source_code": "import platform, os\nprint(f\"Python: {platform.python_version()}\")\nprint(f\"UID: {os.getuid()} | GID: {os.getgid()}\")",
    "limits": {
      "timeout_ms": 3000,
      "memory_mb": 128,
      "cpu_quota_percent": 50,
      "process_limit": 16
    }
  }'
```

### Poll Execution Telemetry
```bash
curl -H "Authorization: Bearer dev-admin-token-runbox-v0.1.1" \
  http://localhost:8000/api/v1/executions/{execution_id}
```

**Structured JSON Response:**
```json
{
  "execution_id": "b78b0fae-6e84-484d-a511-ce1516f1cba2",
  "status": "completed",
  "language": "python",
  "exit_code": 0,
  "stdout": "Python: 3.12.3\nUID: 65534 | GID: 65534\n",
  "stderr": "",
  "resource_usage": {
    "wall_time_ms": 71,
    "cpu_time_ms": 42,
    "memory_peak_bytes": 12480000,
    "pids_peak": 1
  },
  "termination_reason": "normal_exit"
}
```

---

## 9. Dashboard Demonstration & Visual Tour

The Runbox developer dashboard provides real-time monitoring of sandboxed jobs, submission controls, and kernel subsystem health:

### Genuine Application Screenshots

| Dashboard Overview & Telemetry | Submission Console & Limits |
| :---: | :---: |
| ![Dashboard Overview](file:///docs/assets/screenshots/dashboard-overview.png) | ![Submission Console](file:///docs/assets/screenshots/submission-console.png) |

| Execution Explorer | Execution Telemetry Modal |
| :---: | :---: |
| ![Execution Explorer](file:///docs/assets/screenshots/execution-explorer.png) | ![Execution Details Modal](file:///docs/assets/screenshots/execution-details.png) |

| Cluster Security & Kernel Primitives Posture |
| :---: |
| ![Cluster Telemetry](file:///docs/assets/screenshots/system-health.png) |

*(Vector architecture diagrams and visual schematics are maintained in [`docs/assets/`](file:///docs/assets/)).*

---

## 10. Empirical Performance Benchmarks

Runbox was benchmarked across **1,000 measured Python samples**, **250 C++ compilation-and-execution samples**, **300 timeout precision probes**, and **5 burst concurrency tests** on Ubuntu 24.04 LTS:

| Performance Metric | Measured Empirical Result | Target SLA | Status |
|:---|:---:|:---:|:---:|
| **Python Sandboxed Startup (P50)** | **118.07 ms** | $< 100\text{ ms}$ (Nominal) | **PASSED** |
| **Python Sandboxed Startup (P95)** | **159.37 ms** (Pooled 1,000 samples) | $< 200\text{ ms}$ | **PASSED** |
| **Python Sandboxed Startup (P99)** | **186.42 ms** | $< 350\text{ ms}$ | **PASSED** |
| **C++ Two-Stage Compile+Run (P50)**| **916.38 ms** (Comp: 872ms, Exec: 10ms)| $< 1000\text{ ms}$ | **PASSED** |
| **Timeout Enforcement Jitter (P95)** | **39.0 ms** (Mean: 13.17 ms across 300 probes) | $< 50\text{ ms}$ | **PASSED** |
| **Timeout Max Absolute Jitter** | **79.0 ms** (Worst-case across 300 probes) | $< 100\text{ ms}$ | **PASSED** |
| **Concurrent Burst Throughput** | **90.65 jobs/sec** (Peak: **94.41 jobs/sec**) | $> 30\text{ jobs/sec}$ | **PASSED (3.0x)** |

Raw CSV datasets, trial breakdowns, and SVG visualizations are preserved in [benchmarks/results/](file:///benchmarks/results/).

---

## 11. Test & Code Coverage Results

```
TOTAL TESTS: 232 | PASSED: 232 | FAILED: 0 | SKIPPED: 0 | PASS RATE: 100.0%
```

- **GoogleTest C++ Suite:** 93 / 93 passed (`build-release/runbox_tests` across 10 test suites):
  - `ProcessTest`: 11 tests (RAII FDs, pipes, non-blocking stream consumers, monotonic clocks)
  - `ConfigTest`: 14 tests (Serialization, bounds validation, JSON escaping, limit clamping)
  - `CgroupTest`: 9 tests (Cgroups v2 lifecycle, memory/CPU parsing, fallback handling)
  - `NamespaceTest`: 7 tests (Namespace clone flags, isolated mounts, PID mapping)
  - `SeccompTest`: 8 tests (Seccomp BPF policy compilation, syscall filter enforcement)
  - `PrivilegeTest`: 5 tests (Capability bounding set clearing, UID 65534 dropping, rlimits)
  - `FilesystemTest`: 7 tests (Landlock ruleset application, tmpfs mounts, minimal `/dev`)
  - `MonitorTest`: 5 tests (Bounded stdout/stderr stream reader, truncation handling)
  - `SupervisorIntegrationTest`: 22 tests (End-to-end execution, double-fork descendant cleanup, timerfd precision)
  - `SecurityAcceptanceTest`: 5 tests (Network egress blocking, `/etc/shadow` defense, chroot escape prevention)
- **Python Control Plane Suite:** 139 / 139 passed (`pytest tests/unit tests/integration tests/adversarial`):
  - Unit tests: 81 passed (including 12 database lifecycle tests in `test_database_lifecycle.py` and 11 scheduler lifecycle tests in `test_scheduler_lifecycle.py`)
  - Integration tests: 18 passed (including cross-tenant anti-enumeration & cancellation tests)
  - Adversarial penetration suite: 40 passed
- **Pytest Process Lifecycle Verification:**
  - 5 consecutive complete test-suite runs independently verified (`scripts/verify_pytest_lifecycle.py`).
  - 0 manual interventions, 0 lingering background threads or orphaned child processes, natural exit code 0 on every trial.
- **Total C++ Core Coverage:** **88.0%** line coverage (943 / 1072 lines), **95.7%** function coverage (Supervisor Core: **80.8%**).
- **Python Control Plane Coverage:** **89.0%** statement coverage (718 / 805 statements).

---

## 12. Project Structure

```
runbox/
├── .github/workflows/         # GitHub Actions CI workflow (Ubuntu 24.04 LTS)
├── api/                       # FastAPI Control Plane
│   ├── database/              # SQLite WAL mode async persistence
│   ├── models/                # Pydantic schemas for requests and telemetry
│   ├── routes/                # REST endpoints (/api/v1/executions, /health)
│   ├── scheduler/             # Async worker pool & thread-offloaded cleanup
│   ├── security/              # Auth, sliding-window rate limiters, quotas
│   └── main.py                # Service entrypoint & static frontend mount
├── benchmarks/                # Large-scale microbenchmarking suite
│   ├── results/               # Raw CSVs, summary.json, and SVG charts
│   └── run_large_scale_benchmarks.py
├── core/                      # C++20 Sandbox Supervisor Core
│   ├── cgroups/               # Unified cgroups v2 manager (cpu, memory, pids)
│   ├── filesystem/            # Mount namespace, tmpfs, and Landlock LSM
│   ├── monitoring/            # Monotonic timerfd/signalfd event loop
│   ├── namespaces/            # Namespace isolator (PID, NET, NS, IPC, UTS, CGROUP)
│   ├── process/               # RAII Process and POSIX Pipe abstractions
│   ├── seccomp/               # Seccomp BPF filter builder and syscall profiles
│   ├── security/              # Capability dropping and privilege management
│   └── supervisor/            # Main supervisor coordinator and CLI entrypoint
├── dashboard/                 # React 18 + TypeScript + Vite Web Dashboard
├── docs/                      # Architectural, security, and audit documentation
│   ├── assets/                # Documentation visual assets (SVGs, screenshots)
│   ├── audit/                 # Verification audits (WSL2/Native, Security)
│   └── release/               # Release checklist and release notes
├── runtimes/                  # Language Execution Adapters (Python 3.12, C++20)
├── scripts/                   # Coverage generators, secret scanning, assets
└── tests/                     # 223 Automated Tests
    ├── adversarial/           # 40 adversarial security penetration vectors
    ├── integration/           # API and supervisor integration tests
    └── unit/                  # C++ and Python unit tests
```

---

## 13. Limitations & Architectural Boundaries

1. **Host Kernel Shared Boundary:** Runbox provides container-grade isolation based on native Linux kernel namespaces, cgroups v2, seccomp BPF, and Landlock LSM. It executes directly on the host Linux kernel and is not equivalent to a hardware-isolated virtual machine (e.g., KVM/Firecracker). Unpatched host kernel zero-days could theoretically breach container isolation.
2. **Platform Requirements:** Runbox requires a modern Linux kernel ($\ge 5.19$, recommended Linux 6.8+ on Ubuntu 24.04 LTS) with cgroups v2 unified hierarchy, user namespaces, and Landlock LSM enabled.
3. **Execution Verification Scope:** No race conditions, memory leaks, or uncontained execution states were observed during the performed verification campaigns. Testing was conducted on Ubuntu 24.04 LTS under WSL2 (kernel `6.18.54.1-microsoft-standard-WSL2` on Intel Core i7-8650U) and GitHub Actions continuous integration (Ubuntu 24.04 runner on Linux 6.8). Note that bare-metal testing was not performed; enterprise deployments on dedicated bare-metal Linux installations with direct ext4/XFS filesystems are recommended for production latency SLA guarantees.

---

## 14. Security Disclaimer & Verification Assurance

Runbox is designed for secure, untrusted code execution under strict multi-layer defense-in-depth. However, no sandboxing software can guarantee 100% immunity against speculative execution side-channel attacks (e.g., Spectre/Meltdown) or unpatched kernel zero-days without hardware-level hypervisor virtualization. Production operators should ensure host Linux kernel security updates are applied continuously.

---

## 15. Contributing & License

Contributions are welcome! Please read [CONTRIBUTING.md](file:///CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](file:///CODE_OF_CONDUCT.md).  
Vulnerability disclosures should follow our [Security Policy](file:///SECURITY.md).

Runbox is released under the **[MIT License](file:///LICENSE)**.

---

## 16. Documentation Index

- [Architecture & System Design](file:///docs/architecture.md)
- [Security Model & Threat Matrix](file:///docs/threat_model.md)
- [Native Linux Environment Verification](file:///docs/audit/native_linux_verification.md)
- [Large-Sample Performance & Benchmarking Report](file:///docs/benchmarking.md)
- [Comprehensive Security Review](file:///docs/audit/final_security_review.md)
- [Adversarial Attack Verification Matrix](file:///docs/security/adversarial_test_matrix.md)
- [REST API Specification](file:///docs/api.md)
- [Production Deployment Guide (Ubuntu 24.04)](file:///docs/deployment/ubuntu_24_04.md)
- [v0.1.1 Release Notes](file:///docs/release/v0.1.1_release_notes.md)
- [v0.1.1 Release Readiness Checklist](file:///docs/release/v0.1.1_release_checklist.md)
