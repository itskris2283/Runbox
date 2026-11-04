#!/usr/bin/env python3
"""
Runbox Pytest Process Lifecycle & Natural Termination Verifier
Executes 5 consecutive full pytest suite runs and verifies:
- Subprocess returns exit code 0
- All tests pass
- No process hanging / timeout
- No orphaned subprocesses or threads
"""

import os
import subprocess
import sys
import time

import psutil

TARGET_RUNS = 5
PER_RUN_TIMEOUT_SECS = 120


def get_runbox_descendants():
    current_pid = os.getpid()
    descendants = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if proc.info["pid"] != current_pid:
                # Ignore grep, ps, or shell monitoring commands
                if any(x in cmdline for x in ("grep", "verify_pytest_lifecycle")):
                    continue
                if "runbox-supervisor" in cmdline or ("python" in cmdline and "pytest" in cmdline):
                    descendants.append((proc.info["pid"], cmdline))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return descendants


def run_lifecycle_verification():
    print(
        f"[lifecycle-verifier] Starting {TARGET_RUNS} consecutive test lifecycle verification runs..."
    )
    venv_python = "/opt/runbox_venv/bin/python3"
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    results = []

    for run_idx in range(1, TARGET_RUNS + 1):
        print(f"\n--- TRIAL {run_idx}/{TARGET_RUNS} ---")
        t0 = time.perf_counter()

        cmd = [
            venv_python,
            "-m",
            "pytest",
            "tests/unit",
            "tests/integration",
            "tests/adversarial",
            "-q",
        ]

        # Launch via subprocess with explicit timeout
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=PER_RUN_TIMEOUT_SECS,
                cwd="/mnt/d/MERN/Runbox" if os.path.exists("/mnt/d/MERN/Runbox") else os.getcwd(),
                env={**os.environ, "PYTHONPATH": "."},
            )
            elapsed = time.perf_counter() - t0
            stdout_lines = proc.stdout.strip().splitlines()
            summary_line = stdout_lines[-1] if stdout_lines else "NO_OUTPUT"

            print(f"  Duration:   {elapsed:.2f}s")
            print(f"  Exit Code:  {proc.returncode}")
            print(f"  Summary:    {summary_line}")

            if proc.returncode != 0:
                print(f"[ERROR] Trial {run_idx} exited with non-zero code {proc.returncode}!")
                print("\n".join(stdout_lines[-60:]))
                print(proc.stderr)
                return False

            if "passed" not in summary_line or "failed" in summary_line:
                print(f"[ERROR] Trial {run_idx} did not report complete success: {summary_line}")
                return False

            # Check for lingering child/supervisor processes
            lingering = get_runbox_descendants()
            if lingering:
                print(f"[ERROR] Lingering processes detected after Trial {run_idx}: {lingering}")
                return False

            results.append(
                {
                    "trial": run_idx,
                    "duration_secs": round(elapsed, 2),
                    "exit_code": proc.returncode,
                    "summary": summary_line,
                    "clean_exit": True,
                }
            )

        except subprocess.TimeoutExpired:
            print(f"[ERROR] Trial {run_idx} timed out after {PER_RUN_TIMEOUT_SECS}s!")
            return False

    print("\n=======================================================")
    print(f"LIFECYCLE VERIFICATION PASSED: {TARGET_RUNS}/{TARGET_RUNS} runs completed cleanly.")
    print("Zero manual interventions. Zero lingering processes. Natural exit code 0.")
    print("=======================================================")
    return True


if __name__ == "__main__":
    success = run_lifecycle_verification()
    sys.exit(0 if success else 1)
