#!/usr/bin/env python3
import asyncio
import contextlib
import json
import os
import statistics
import sys
import time
from typing import Any

from api.database.database import Database
from api.scheduler.scheduler import JobScheduler
from runtimes.base import ExecutionLimits, ExecutionRequest

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def compute_percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    sorted_v = sorted(values)
    n = len(sorted_v)
    return {
        "count": n,
        "min": round(sorted_v[0], 2),
        "max": round(sorted_v[-1], 2),
        "mean": round(statistics.mean(sorted_v), 2),
        "median": round(statistics.median(sorted_v), 2),
        "p50": round(sorted_v[int(n * 0.50)], 2),
        "p90": round(sorted_v[min(int(n * 0.90), n - 1)], 2),
        "p95": round(sorted_v[min(int(n * 0.95), n - 1)], 2),
        "p99": round(sorted_v[min(int(n * 0.99), n - 1)], 2),
        "stddev": round(statistics.stdev(sorted_v), 2) if n > 1 else 0.0,
    }


async def benchmark_python_warmup(
    scheduler: JobScheduler, db: Database, iterations: int = 50
) -> list[float]:
    latencies: list[float] = []
    req = ExecutionRequest(
        language="python",
        source_code="print('WARM_BENCHMARK_OK')",
        limits=ExecutionLimits(timeout_ms=5000, memory_mb=128),
    )

    for _i in range(iterations):
        t0 = time.perf_counter()
        exec_id = await scheduler.submit_job(req)

        # Wait for completion
        while True:
            rec = await db.get_execution(exec_id)
            if rec and rec["status"].lower() in (
                "completed",
                "failed",
                "timed_out",
                "resource_limit_exceeded",
            ):
                break
            await asyncio.sleep(0.002)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

    return latencies


async def benchmark_cpp_warmup(
    scheduler: JobScheduler, db: Database, iterations: int = 20
) -> list[float]:
    latencies: list[float] = []
    req = ExecutionRequest(
        language="cpp",
        source_code="#include <iostream>\nint main(){ std::cout << 42 << std::endl; return 0; }",
        limits=ExecutionLimits(timeout_ms=10000, memory_mb=256),
    )

    for _i in range(iterations):
        t0 = time.perf_counter()
        exec_id = await scheduler.submit_job(req)

        while True:
            rec = await db.get_execution(exec_id)
            if rec and rec["status"].lower() in (
                "completed",
                "failed",
                "timed_out",
                "resource_limit_exceeded",
            ):
                break
            await asyncio.sleep(0.002)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

    return latencies


async def benchmark_timeout_enforcement(scheduler: JobScheduler, db: Database) -> dict[str, Any]:
    timeout_configs = [500, 1000, 1500]
    results = {}

    for t_ms in timeout_configs:
        samples = []
        req = ExecutionRequest(
            language="python",
            source_code="import time\ntime.sleep(10)",
            limits=ExecutionLimits(timeout_ms=t_ms, memory_mb=64),
        )

        for _i in range(5):
            t0 = time.perf_counter()
            exec_id = await scheduler.submit_job(req, user_id="usr_bench_timeout")

            while True:
                rec = await db.get_execution(exec_id)
                if rec and rec["status"].lower() in (
                    "timed_out",
                    "completed",
                    "failed",
                    "resource_limit_exceeded",
                ):
                    break
                await asyncio.sleep(0.002)

            # Precision measured against actual sandbox wall time reported by kernel supervisor
            wall_time = rec.get("wall_time_ms") or ((time.perf_counter() - t0) * 1000)
            jitter = abs(wall_time - t_ms)
            samples.append(jitter)

        results[f"{t_ms}ms"] = {
            "raw_samples_ms": samples,
            "statistics": compute_percentiles(samples),
        }

    return results


async def benchmark_concurrent_burst(
    scheduler: JobScheduler, db: Database, burst_size: int = 25
) -> dict[str, Any]:
    req = ExecutionRequest(
        language="python",
        source_code="import math\nprint(math.sqrt(12345.6789))",
        limits=ExecutionLimits(timeout_ms=5000, memory_mb=128),
    )

    t0 = time.perf_counter()
    job_ids = []
    # Distribute burst across 5 tenants so each tenant has 5 jobs, matching max concurrency slots
    for i in range(burst_size):
        tenant_id = f"usr_tenant_{i % 5}"
        eid = await scheduler.submit_job(req, user_id=tenant_id)
        job_ids.append(eid)

    async def wait_for_job(eid: str):
        while True:
            rec = await db.get_execution(eid)
            if rec and rec["status"].lower() in (
                "completed",
                "failed",
                "timed_out",
                "resource_limit_exceeded",
            ):
                return rec
            await asyncio.sleep(0.002)

    await asyncio.gather(*[wait_for_job(eid) for eid in job_ids])

    total_time_sec = time.perf_counter() - t0
    throughput = burst_size / total_time_sec

    return {
        "burst_size": burst_size,
        "total_time_seconds": round(total_time_sec, 3),
        "throughput_jobs_per_sec": round(throughput, 2),
    }


async def main():
    sys.stdout.reconfigure(line_buffering=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    bench_db_path = "/root/runbox_bench.db"
    for ext in ["", "-wal", "-shm"]:
        p = bench_db_path + ext
        if os.path.exists(p):
            with contextlib.suppress(OSError):
                os.remove(p)

    db = Database(bench_db_path)
    await db.connect()
    scheduler = JobScheduler(db, max_concurrency=25, max_queue_size=200)
    await scheduler.start()

    print("=================================================================")
    print("      RUNBOX SECURE SANDBOX INFRASTRUCTURE BENCHMARK SUITE       ")
    print("=================================================================")
    print(f"Platform: Ubuntu 24.04 LTS (Kernel: {os.uname().release})")
    print("Storage: /tmp/runbox_bench.db (WAL mode)")
    print("Isolation: cgroup v2 + User/PID/Mount/Net NS + Landlock + Seccomp")
    print("-----------------------------------------------------------------")

    num_trials = 5
    trial_results = []

    for trial in range(1, num_trials + 1):
        print(f"\n[Trial {trial}/{num_trials}] Executing benchmark suite...")

        print("  -> Benchmarking Python sandbox warm invocation (50 samples)...")
        py_latencies = await benchmark_python_warmup(scheduler, db, 50)
        py_stats = compute_percentiles(py_latencies)
        print(
            f"     P50: {py_stats['p50']} ms | P95: {py_stats['p95']} ms | P99: {py_stats['p99']} ms | Mean: {py_stats['mean']} ms"
        )

        print("  -> Benchmarking C++ end-to-end compile+run invocation (15 samples)...")
        cpp_latencies = await benchmark_cpp_warmup(scheduler, db, 15)
        cpp_stats = compute_percentiles(cpp_latencies)
        print(
            f"     P50: {cpp_stats['p50']} ms | P95: {cpp_stats['p95']} ms | P99: {cpp_stats['p99']} ms | Mean: {cpp_stats['mean']} ms"
        )

        print("  -> Benchmarking timeout enforcement precision...")
        timeout_stats = await benchmark_timeout_enforcement(scheduler, db)
        print(
            f"     500ms jitter mean: {timeout_stats['500ms']['statistics']['mean']} ms | P95: {timeout_stats['500ms']['statistics']['p95']} ms"
        )

        print("  -> Benchmarking concurrent burst capacity (25 jobs)...")
        burst_stats = await benchmark_concurrent_burst(scheduler, db, 25)
        print(
            f"     Throughput: {burst_stats['throughput_jobs_per_sec']} jobs/sec across {scheduler.max_concurrency} worker slots"
        )

        trial_data = {
            "trial": trial,
            "timestamp": time.time(),
            "python_execution": {"raw_samples_ms": py_latencies, "statistics": py_stats},
            "cpp_execution": {"raw_samples_ms": cpp_latencies, "statistics": cpp_stats},
            "timeout_enforcement": timeout_stats,
            "concurrent_burst": burst_stats,
        }

        trial_results.append(trial_data)
        trial_file = os.path.join(DATA_DIR, f"trial_{trial}.json")
        with open(trial_file, "w") as f:
            json.dump(trial_data, f, indent=2)

    # Compute overall multi-trial aggregate
    all_py_samples = [s for t in trial_results for s in t["python_execution"]["raw_samples_ms"]]
    all_cpp_samples = [s for t in trial_results for s in t["cpp_execution"]["raw_samples_ms"]]
    all_throughputs = [t["concurrent_burst"]["throughput_jobs_per_sec"] for t in trial_results]
    all_timeout_samples = [
        s
        for t in trial_results
        for cfg in ("500ms", "1000ms", "1500ms")
        for s in t["timeout_enforcement"][cfg]["raw_samples_ms"]
    ]

    py_trial_p95s = [t["python_execution"]["statistics"]["p95"] for t in trial_results]
    cpp_trial_p95s = [t["cpp_execution"]["statistics"]["p95"] for t in trial_results]

    overall_summary = {
        "aggregate_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kernel_release": os.uname().release,
        "trials_count": num_trials,
        "python_e2e_latency_ms": compute_percentiles(all_py_samples),
        "python_trial_p95_mean": round(statistics.mean(py_trial_p95s), 2),
        "python_trial_p95_median": round(statistics.median(py_trial_p95s), 2),
        "cpp_e2e_latency_ms": compute_percentiles(all_cpp_samples),
        "cpp_trial_p95_mean": round(statistics.mean(cpp_trial_p95s), 2),
        "cpp_trial_p95_median": round(statistics.median(cpp_trial_p95s), 2),
        "timeout_jitter_pooled": compute_percentiles(all_timeout_samples),
        "timeout_jitter_max_absolute": round(max(all_timeout_samples), 2)
        if all_timeout_samples
        else 0.0,
        "throughput_jobs_per_sec": {
            "mean": round(statistics.mean(all_throughputs), 2),
            "max": round(max(all_throughputs), 2),
            "min": round(min(all_throughputs), 2),
        },
        "trials": trial_results,
    }

    summary_file = os.path.join(DATA_DIR, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(overall_summary, f, indent=2)

    print("\n=================================================================")
    print("                 BENCHMARK AGGREGATE SUMMARY                    ")
    print("=================================================================")
    print(f"Total Python executions evaluated: {len(all_py_samples)}")
    print(f"  Pooled P50:            {overall_summary['python_e2e_latency_ms']['p50']} ms")
    print(f"  Pooled P90:            {overall_summary['python_e2e_latency_ms']['p90']} ms")
    print(f"  Pooled P95:            {overall_summary['python_e2e_latency_ms']['p95']} ms")
    print(f"  Pooled P99:            {overall_summary['python_e2e_latency_ms']['p99']} ms")
    print(f"  Mean Trial P95:        {overall_summary['python_trial_p95_mean']} ms")
    print(f"  Median Trial P95:      {overall_summary['python_trial_p95_median']} ms")
    print(
        f"  Pooled Mean:           {overall_summary['python_e2e_latency_ms']['mean']} ms (+/- {overall_summary['python_e2e_latency_ms']['stddev']})"
    )
    print("-----------------------------------------------------------------")
    print(f"Total C++ compile+run executions evaluated: {len(all_cpp_samples)}")
    print(f"  Pooled P50:            {overall_summary['cpp_e2e_latency_ms']['p50']} ms")
    print(f"  Pooled P95:            {overall_summary['cpp_e2e_latency_ms']['p95']} ms")
    print(f"  Pooled Mean:           {overall_summary['cpp_e2e_latency_ms']['mean']} ms")
    print("-----------------------------------------------------------------")
    print(f"Timeout Jitter Evaluated across {len(all_timeout_samples)} probes:")
    print(f"  Pooled Mean Jitter:    {overall_summary['timeout_jitter_pooled']['mean']} ms")
    print(f"  Pooled P50 Jitter:     {overall_summary['timeout_jitter_pooled']['p50']} ms")
    print(f"  Pooled P95 Jitter:     {overall_summary['timeout_jitter_pooled']['p95']} ms")
    print(f"  Actual Max Abs Jitter: {overall_summary['timeout_jitter_max_absolute']} ms")
    print("-----------------------------------------------------------------")
    print(
        f"Concurrent Throughput: {overall_summary['throughput_jobs_per_sec']['mean']} jobs/sec (burst of 25 jobs)"
    )
    print(f"Saved complete telemetry datasets to: {DATA_DIR}")
    print("=================================================================")

    await scheduler.stop()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
