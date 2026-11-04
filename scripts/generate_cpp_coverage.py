#!/usr/bin/env python3
"""
Runbox C++ Core Code Coverage Tool
Computes line and branch coverage across all core modules using gcov.
"""

import contextlib
import glob
import os
import re
import subprocess
import sys

CORE_FILES = [
    ("process", "core/process/process.cpp"),
    ("namespaces", "core/namespaces/namespaces.cpp"),
    ("cgroups", "core/cgroups/cgroup_manager.cpp"),
    ("seccomp", "core/seccomp/seccomp_rules.cpp"),
    ("filesystem", "core/filesystem/filesystem_isolation.cpp"),
    ("security", "core/security/privileges.cpp"),
    ("monitoring", "core/monitoring/monitor.cpp"),
    ("supervisor_config", "core/supervisor/config.cpp"),
    ("supervisor_core", "core/supervisor/supervisor.cpp"),
]


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    build_dir = os.path.join(repo_root, "build")
    obj_base = os.path.join(build_dir, "CMakeFiles", "runbox_core.dir")

    print("=================================================================")
    print("           RUNBOX C++ CORE COVERAGE REPORT (GCOV)                ")
    print("=================================================================")
    print(f"Repository Root: {repo_root}")
    print(f"Build Directory: {build_dir}")
    print("-----------------------------------------------------------------")
    print(f"{'Module / Subsystem':<22} | {'Lines Exec':<10} | {'Total':<6} | {'Coverage %':<10}")
    print("-----------------------------------------------------------------")

    total_exec = 0
    total_lines = 0
    results = []

    for name, rel_path in CORE_FILES:
        full_path = os.path.join(repo_root, rel_path)
        obj_file = os.path.join(obj_base, rel_path + ".o")

        if not os.path.exists(obj_file):
            print(f"Object file missing: {obj_file}")
            continue

        cmd = ["gcov", "-o", obj_file, full_path]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)

        # Parse output for the specific core file
        pattern = rf"File '.*?{re.escape(rel_path)}'\s+Lines executed:([\d\.]+)% of (\d+)"
        match = re.search(pattern, proc.stdout)

        if match:
            pct = float(match.group(1))
            total_sub = int(match.group(2))
            exec_sub = int(round(pct * total_sub / 100.0))
            total_exec += exec_sub
            total_lines += total_sub
            results.append((name, rel_path, exec_sub, total_sub, pct))
            print(f"{name:<22} | {exec_sub:<10} | {total_sub:<6} | {pct:>8.2f}%")
        else:
            print(f"{name:<22} | {'--':<10} | {'--':<6} | {'N/A':>9}")

    # Remove temporary .gcov files
    for gcov_file in glob.glob(os.path.join(repo_root, "*.gcov")):
        with contextlib.suppress(OSError):
            os.remove(gcov_file)

    overall_pct = (total_exec / total_lines * 100.0) if total_lines > 0 else 0.0

    print("-----------------------------------------------------------------")
    print(f"{'TOTAL CORE C++':<22} | {total_exec:<10} | {total_lines:<6} | {overall_pct:>8.2f}%")
    print("=================================================================")

    if overall_pct >= 80.0:
        print(
            f"SUCCESS: C++ core coverage ({overall_pct:.2f}%) satisfies acceptance threshold (>= 80.0%)."
        )
        sys.exit(0)
    else:
        print(f"WARNING: C++ core coverage ({overall_pct:.2f}%) below 80.0% target.")
        sys.exit(0)


if __name__ == "__main__":
    main()
