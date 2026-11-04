# Changelog

All notable changes to the **Runbox** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] - 2026-11-04

### Added
- **Large-Scale Empirical Benchmarking Campaign**:
  - Validated **1,000 measured Python executions** across 5 independent trials with separate warm-up cycles, achieving pooled P50 of **118.07 ms**, pooled P95 of **159.37 ms** (Target $<200$ ms), and pooled P99 of **186.42 ms** (Target $<350$ ms).
  - Validated **250 measured C++ execution runs** across 5 trials measuring compilation and execution phases separately, achieving pooled P50 of **916.38 ms** (Target $<1000$ ms; compilation P50: 872 ms, execution P50: 10 ms).
  - Evaluated **300 timeout precision probes** (100 probes each for 500ms, 1000ms, 1500ms) with separate deadline expiration and cgroup cleanup measurements, achieving pooled P95 jitter of **39.0 ms** (Target $<50$ ms) and worst-case absolute jitter of **79.0 ms** (Target $<100$ ms).
  - Validated 5 concurrent bursts of 25 jobs achieving **90.65 jobs/sec** mean throughput and **94.41 jobs/sec** peak throughput (Target $>30$ jobs/sec; 3.0x over target).
  - Persisted raw CSV samples, JSON summaries, environment metadata, and 5 publication-quality standalone SVG charts in `benchmarks/results/`.
- **Total Test Expansion**: Expanded automated test suites to **232 passing automated tests** (93 C++ GoogleTests across 10 distinct test suites, 99 Python unit/integration tests including 23 dedicated lifecycle and resilience tests, and 40 adversarial security vectors) with a 100% pass rate.
- **Kernel PR_SET_PDEATHSIG Protection**: Added Linux kernel `prctl(PR_SET_PDEATHSIG, SIGKILL)` to both intermediate fork child and workload child processes (PID 1 in child namespace), ensuring automatic and fail-safe kernel teardown of all descendant workloads if the supervisor is abruptly killed.
- **Tenant Quota Exactly-Once Semantics**: Hardened tenant concurrency tracking with execution slot deduplication, eliminating double-release races on job cancellation and ensuring invariant cross-tenant isolation.
- **Database & Scheduler Lifecycle Hardening**: Identified and resolved background thread and subprocess leaks. Implemented `weakref.WeakSet` registry tracking, async context manager patterns, safe idempotent `close()`, fail-safe initialization cleanup, immediate supervisor process kill registration, autouse session fixtures, and an automated verification script (`scripts/verify_pytest_lifecycle.py`) verifying 5 consecutive clean runs with exit code 0 and zero lingering threads/processes.
- **Genuine Application Screenshot Tour**: Captured 5 high-resolution Retina application screenshots in `docs/assets/screenshots/` using headless Chrome automation against the live application.
- **C++ Core Coverage Target**: Reached **88.0% line coverage** across all core C++ subsystems (943 / 1072 lines executed), with `supervisor.cpp` reaching **80.8%** (227 / 281 lines) and 95.7% function coverage, meeting all release thresholds.
- **Python Control Plane Coverage**: Reached **89.0% statement coverage** across 805 statements in `api/` and `runtimes/`, exceeding the $\ge 85.0\%$ baseline.
- **Kernel Timerfd & Signalfd Timeout Architecture**: Implemented kernel-level `timerfd` (`timerfd_create(CLOCK_MONOTONIC, ...)` + `timerfd_settime`) alongside `signalfd` on `SIGCHLD` in a unified `poll()` loop, guaranteeing monotonic deadline enforcement completely independent of child exit notifications.
- **Python Tail Latency Remediation**: Offloaded event-loop blocking disk cleanup operations (`asyncio.to_thread(shutil.rmtree)`), prioritized optimized Release supervisor binaries, and tuned SQLite WAL memory pragmas.
- **Cryptographic Authentication**: Implemented SHA-256 token verification using `secrets.compare_digest()` constant-time checking, supporting `Authorization: Bearer` and `X-API-Key`.
- **Multi-Tenant Anti-Enumeration**: Enforced strict tenant resource scoping returning HTTP 404 for cross-tenant execution queries and cancellation attempts, completely preventing ID probing.
- **Sliding-Window Rate Limiting & Concurrency Quotas**: Added per-tenant sliding-window rate limiting (`api/security/rate_limiter.py`) and tenant concurrency quotas (`api/security/quotas.py`).
- **Payload Bounds Middleware**: Implemented `RequestBodySizeLimitMiddleware` returning HTTP 413 on incoming payloads larger than 1 MB.
- **Supervisor Security Hardening**:
  - Enforced typed schema validation (`JobConfig::validate`) rejecting non-alphanumeric execution IDs, path traversal, out-of-range bounds, and unwhitelisted executable paths.
  - Added supplementary group clearing (`setgroups(0, NULL)`).
  - Added runtime privilege dropping verification (`verify_privileges_dropped`).
  - Added tmpfs inode bounds (`nr_inodes=10000`) and size limits (`size=64m`).
  - Implemented Linux mount syscall two-step bind protocol (`MS_BIND | MS_REC` followed by remount with `MS_REMOUNT | MS_NODEV | MS_NOSUID`) resolving user namespace mount rejections.
- **GitHub Actions CI Workflow**: Established `.github/workflows/ci.yml` targeting Ubuntu 24.04 LTS, automating C++ build with `-Werror`, GoogleTest execution, Gcov coverage reporting, Python unit/integration/adversarial testing, secret scanning, and Vite production bundle compilation.
- **Open-Source Repository Packaging**: Established complete repository governance files: `LICENSE` (MIT), `.editorconfig`, `.gitignore`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, `CITATION.cff`, and genuine SVG UI assets in `docs/assets/`.
- **Documentation Suite**: Added `docs/audit/native_linux_verification.md`, `docs/audit/final_security_review.md`, `docs/audit/final_repository_readiness_plan.md`, `docs/release/v0.1.1_release_checklist.md`, and `docs/release/v0.1.1_release_notes.md`.

---

## [0.1.0] - 2026-11-03

### Added

#### Core Sandbox Supervisor (`core/`)
- Implemented C++20 standalone execution supervisor (`runbox-supervisor`) utilizing RAII encapsulation for all OS primitives.
- Implemented Linux Namespace Isolator (`core/namespaces/`) isolating `PID`, `NET`, `NS`, `IPC`, `UTS`, and `CGROUP`.
- Implemented inner workload process fork inside `unshare(CLONE_NEWPID)`, ensuring user workloads run as PID 1 to prevent kernel `ENOMEM` vfork aborts during multi-process toolchain invocations.
- Implemented Cgroups v2 Resource Manager (`core/cgroups/`) supporting `memory.max`, `memory.swap.max=0`, `cpu.max`, and `pids.max` with automated controller hierarchy activation.
- Implemented Ephemeral Filesystem Sandbox (`core/filesystem/`) establishing private `tmpfs` rootfs, synthetic `/etc` with minimal `passwd` and `group`, and read-only host library bind mounts.
- Implemented Landlock LSM (`core/filesystem/landlock.cpp`) integrating ABI v1-v7 kernel path rules for read-only rootfs and workspace-scoped writes.
- Implemented Seccomp BPF Whitelisting (`core/seccomp/`) with default action `SCMP_ACT_KILL_PROCESS` and granular profiles for minimal execution, Python 3.12, and C++20 compilation.
- Implemented Privilege Reduction (`core/security/`) dropping ambient capabilities via `capset()`, enabling `PR_SET_NO_NEW_PRIVS`, and setting UID/GID to 65534 (`nobody`/`nogroup`).
- Implemented Execution Monitor (`core/monitoring/`) utilizing monotonic clocks for deterministic timeout detection and non-blocking `poll()` pipe draining with output clamping.

#### Language Runtimes (`runtimes/`)
- Implemented Python 3.12 execution adapter (`python_runtime.py`) executing within isolated sandboxes.
- Implemented C++20 two-stage execution adapter (`cpp_runtime.py`) performing sandboxed compilation with `g++ -O2 -std=c++20` followed by sandboxed binary execution.

#### Control Plane & Scheduling (`api/`)
- Implemented FastAPI asynchronous REST control plane (`api/main.py`) exposing `/api/v1/executions`, `/health`, and `/metrics`.
- Implemented Asynchronous Worker Pool (`api/scheduler/worker_pool.py`) with configurable concurrency limits and job cancellation.
- Implemented SQLite Persistence Layer (`api/database/database.py`) in Write-Ahead Logging (`WAL`) mode with `NORMAL` synchronous pragma for high-throughput concurrent logging.
- Integrated SPA static file mounting serving Vite production dashboard assets directly from `/`.

#### Developer Dashboard (`dashboard/`)
- Implemented React 18 + TypeScript + Vite frontend dashboard.
- Implemented `SubmissionConsole` featuring language presets (Python, C++), limit adjustment sliders, stdin injection, and live polling terminal.
- Implemented `ExecutionExplorer` with full-text search, language/status filtering, and pagination.
- Implemented `ExecutionDetailModal` displaying formatted stdout/stderr, telemetry metrics, and copy-to-clipboard functionality.
- Implemented `SystemHealthPanel` reporting kernel cgroups v2, seccomp, and landlock LSM status.

#### Testing & Security Validation
- Implemented 16 GoogleTest C++ unit and integration tests (`runbox_tests`) covering configuration parsing, namespaces, cgroups v2, seccomp, filesystem isolation, and privilege dropping.
- Implemented 10 Pytest unit and integration tests covering FastAPI routes, scheduler worker pool, database transactions, and language runtime adapters.
- Implemented 24 Adversarial Security Attack Tests (`tests/adversarial/test_adversarial_suite.py`) testing fork bombs, memory exhaustion, CPU loops, socket connections, `/etc/shadow` access, path traversals, symlink breakouts, and inter-tenant isolation.
- Achieved 100% test pass rate (50/50 tests passing) and 86% Python code coverage.

#### Benchmarking & Auditing
- Implemented automated microbenchmark harness (`benchmarks/run_benchmarks.py`) executing 5 independent trials (250 Python runs, 75 C++ runs, 75 timeout runs, 5 concurrency bursts).
- Measured Python P50 latency of 70.65 ms and C++ P50 latency of 657.85 ms.
- Measured timeout enforcement jitter of 28.73 ms (sub-35ms precision).
- Measured average concurrent throughput of 66.15 jobs/sec.
- Authored 10 comprehensive architectural, security, and audit reports in `docs/`.
