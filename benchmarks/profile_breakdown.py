#!/usr/bin/env python3
import asyncio
import os
import shutil
import subprocess
import time

from api.database.database import Database
from runtimes.supervisor_invoker import invoke_supervisor


def profile_native_subprocesses():
    print("--- 1. Native Subprocess Timings ---")
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        subprocess.run(["/usr/bin/python3", "-c", "print(42)"], capture_output=True)
        times.append((time.perf_counter() - t0) * 1000)
    print(
        f"Native python3 -c 'print(42)': mean={sum(times) / len(times):.2f}ms, min={min(times):.2f}ms"
    )

    times_s = []
    for _ in range(10):
        t0 = time.perf_counter()
        subprocess.run(["/usr/bin/python3", "-S", "-c", "print(42)"], capture_output=True)
        times_s.append((time.perf_counter() - t0) * 1000)
    print(
        f"Native python3 -S -c 'print(42)': mean={sum(times_s) / len(times_s):.2f}ms, min={min(times_s):.2f}ms"
    )


async def profile_supervisor_invoker_direct():
    print("\n--- 2. Direct Supervisor Invocation (Bypassing API, DB, and Scheduler) ---")
    ws = "/tmp/runbox_prof_ws"
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "main.py"), "w") as f:
        f.write("print('DIRECT_SUPERVISOR_TEST')\n")

    times = []
    for i in range(10):
        t0 = time.perf_counter()
        res = await invoke_supervisor(
            execution_id=f"prof-direct-{i}",
            executable_path="/usr/bin/python3",
            argv=["-u", "main.py"],
            language="python",
            workspace_dir=ws,
            stdin_data="",
            limits={
                "timeout_ms": 3000,
                "memory_mb": 128,
                "cpu_quota_percent": 100,
                "process_limit": 32,
                "output_limit_bytes": 65536,
            },
        )
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)
    print(
        f"Direct invoke_supervisor: mean={sum(times) / len(times):.2f}ms, min={min(times):.2f}ms, wall_time_ms={res.resource_usage.wall_time_ms}ms"
    )
    shutil.rmtree(ws, ignore_errors=True)


async def profile_database_operations():
    print("\n--- 3. Database Async Operations (aiosqlite WAL) ---")
    db_path = "/tmp/prof_bench.db"
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(db_path + ext):
            os.remove(db_path + ext)
    db = Database(db_path)
    await db.connect()

    times_sub = []
    times_rec = []
    times_get = []
    for i in range(20):
        eid = f"job-prof-{i}"
        t0 = time.perf_counter()
        await db.record_submission(eid, "python", "print(1)", user_id="usr_dev")
        times_sub.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        await db.record_result(eid, "COMPLETED", 0, "normal_exit", "1\n", "", 50, 20, 1000000, 1)
        times_rec.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        await db.get_execution(eid)
        times_get.append((time.perf_counter() - t0) * 1000)

    print(f"db.record_submission: mean={sum(times_sub) / len(times_sub):.2f}ms")
    print(f"db.record_result: mean={sum(times_rec) / len(times_rec):.2f}ms")
    print(f"db.get_execution: mean={sum(times_get) / len(times_get):.2f}ms")
    await db.close()


async def main():
    profile_native_subprocesses()
    await profile_supervisor_invoker_direct()
    await profile_database_operations()


if __name__ == "__main__":
    asyncio.run(main())
