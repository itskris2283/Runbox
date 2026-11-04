import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from api.database.database import Database


@pytest.fixture
async def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "test_adv.db")
    db = Database(db_path=db_file)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
        if os.path.exists(db_file):
            os.remove(db_file)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


@pytest.mark.asyncio
async def test_recover_stale_executions(temp_db):
    # Insert jobs in different states
    await temp_db.record_submission("job_queued", "python", user_id="usr_a")
    await temp_db.record_submission("job_running", "python", user_id="usr_a")
    await temp_db.update_status("job_running", "RUNNING")
    await temp_db.record_submission("job_completed", "python", user_id="usr_a")
    await temp_db.record_result(
        "job_completed", "COMPLETED", 0, "normal", "out", "", 10, 5, 1024, 1
    )

    # Recover stale executions
    recovered_count = await temp_db.recover_stale_executions()
    assert recovered_count == 2  # job_queued and job_running

    # Verify statuses
    r_queued = await temp_db.get_execution("job_queued")
    assert r_queued["status"] == "FAILED"
    assert r_queued["termination_reason"] == "server_restarted"

    r_running = await temp_db.get_execution("job_running")
    assert r_running["status"] == "FAILED"
    assert r_running["termination_reason"] == "server_restarted"

    r_completed = await temp_db.get_execution("job_completed")
    assert r_completed["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_purge_old_executions(temp_db):
    # Insert recent job
    await temp_db.record_submission("job_recent", "python", user_id="usr_a")

    # Manually insert old job with submitted_at 40 days ago
    old_time = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    await temp_db._conn.execute(
        "INSERT INTO executions (execution_id, user_id, submitted_at, language, status) VALUES (?, ?, ?, ?, ?)",
        ("job_old", "usr_a", old_time, "python", "COMPLETED"),
    )
    await temp_db._conn.commit()

    # Purge older than 30 days
    purged = await temp_db.purge_old_executions(retention_days=30)
    assert purged == 1

    assert await temp_db.get_execution("job_old") is None
    assert await temp_db.get_execution("job_recent") is not None


@pytest.mark.asyncio
async def test_tenant_isolation_get_execution(temp_db):
    await temp_db.record_submission("job_tenant_a", "python", user_id="usr_tenant_a")
    await temp_db.record_submission("job_tenant_b", "python", user_id="usr_tenant_b")

    # Tenant A should not see Tenant B's job
    res = await temp_db.get_execution("job_tenant_b", user_id="usr_tenant_a")
    assert res is None

    # Tenant B should see their own job
    res_b = await temp_db.get_execution("job_tenant_b", user_id="usr_tenant_b")
    assert res_b is not None
    assert res_b["execution_id"] == "job_tenant_b"

    # Admin sees everything
    res_admin = await temp_db.get_execution("job_tenant_b", user_id="usr_admin")
    assert res_admin is not None


@pytest.mark.asyncio
async def test_tenant_isolation_list_executions(temp_db):
    await temp_db.record_submission("job_1_a", "python", user_id="usr_tenant_a")
    await temp_db.record_submission("job_2_a", "python", user_id="usr_tenant_a")
    await temp_db.record_submission("job_1_b", "python", user_id="usr_tenant_b")

    # Tenant A list
    list_a = await temp_db.list_executions(user_id="usr_tenant_a")
    assert len(list_a) == 2
    assert all(r["user_id"] == "usr_tenant_a" for r in list_a)

    # Tenant B list
    list_b = await temp_db.list_executions(user_id="usr_tenant_b")
    assert len(list_b) == 1
    assert list_b[0]["user_id"] == "usr_tenant_b"

    # Admin list
    list_all = await temp_db.list_executions(user_id="usr_admin")
    assert len(list_all) == 3


@pytest.mark.asyncio
async def test_pagination_list_executions(temp_db):
    for i in range(10):
        await temp_db.record_submission(f"job_p_{i:02d}", "python", user_id="usr_a")

    page_1 = await temp_db.list_executions(user_id="usr_a", limit=4, offset=0)
    assert len(page_1) == 4

    page_2 = await temp_db.list_executions(user_id="usr_a", limit=4, offset=4)
    assert len(page_2) == 4

    page_3 = await temp_db.list_executions(user_id="usr_a", limit=4, offset=8)
    assert len(page_3) == 2


@pytest.mark.asyncio
async def test_record_result_comprehensive(temp_db):
    await temp_db.record_submission("job_stats", "cpp", user_id="usr_dev")
    await temp_db.record_result(
        execution_id="job_stats",
        status="COMPLETED",
        exit_code=0,
        termination_reason="normal",
        stdout="computed 42",
        stderr="compilation note",
        wall_time_ms=125,
        cpu_time_ms=88,
        memory_peak_bytes=4194304,
        pids_peak=3,
        compilation_duration_ms=450,
        error_message=None,
    )

    record = await temp_db.get_execution("job_stats")
    assert record["status"] == "COMPLETED"
    assert record["exit_code"] == 0
    assert record["stdout"] == "computed 42"
    assert record["wall_time_ms"] == 125
    assert record["cpu_time_ms"] == 88
    assert record["memory_peak_bytes"] == 4194304
    assert record["pids_peak"] == 3
    assert record["compilation_duration_ms"] == 450


@pytest.mark.asyncio
async def test_metrics_aggregation_counts(temp_db):
    await temp_db.record_submission("m1", "python")
    await temp_db.record_result("m1", "COMPLETED", 0, "normal", "", "", 100, 50, 1024, 1)

    await temp_db.record_submission("m2", "python")
    await temp_db.record_result("m2", "TIMED_OUT", -1, "timeout", "", "", 200, 150, 2048, 2)

    await temp_db.record_submission("m3", "python")
    await temp_db.record_result("m3", "FAILED", 1, "error", "", "", 150, 100, 1024, 1)

    metrics = await temp_db.get_metrics()
    assert metrics["total"] == 3
    assert metrics["completed"] == 1
    assert metrics["timed_out"] == 1
    assert metrics["failed"] == 1
    assert metrics["avg_wall_time_ms"] == 150.0
    assert metrics["avg_cpu_time_ms"] == 100.0
