#!/usr/bin/env python3
import subprocess
import time

t0 = time.perf_counter()
res = subprocess.run(
    [
        "build/runbox-supervisor",
        "--json",
        """{
  "execution_id": "perf-test-fast",
  "language": "python",
  "executable_path": "/usr/bin/python3",
  "argv": ["-c", "print('FAST_OK')"],
  "workspace_dir": "/tmp/ws_fast",
  "stdin": "",
  "limits": {
    "timeout_ms": 3000,
    "memory_mb": 128,
    "cpu_quota_percent": 100,
    "process_limit": 32,
    "output_limit_bytes": 65536
  }
}""",
    ],
    capture_output=True,
    text=True,
)
t1 = time.perf_counter()
print(f"Total runbox-supervisor process execution time: {(t1 - t0) * 1000:.2f} ms")
print(f"Stdout: {res.stdout.strip()}")
