import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from api.database.database import Database
from api.scheduler.scheduler import JobScheduler
from api.security.quotas import quota_manager
from runtimes.base import ExecutionLimits, ExecutionRequest, ExecutionResponse, ResourceUsage


@pytest.fixture
async def temp_scheduler():
    temp_dir = tempfile.mkdtemp()
    db_file = os.path.join(temp_dir, "test_sched.db")
    db = Database(db_path=db_file)
    await db.connect()
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=3)
    await sched.start()
    try:
        yield sched, db
    finally:
        await sched.stop()
        await db.close()
        if os.path.exists(db_file):
            os.remove(db_file)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        quota_manager.reset()


@pytest.mark.asyncio
async def test_scheduler_lifecycle_idempotent(temp_scheduler):
    sched, _ = temp_scheduler
    # Calling start again should be a no-op
    await sched.start()
    assert sched._running is True
    assert len(sched.workers) == 2

    # Calling stop
    await sched.stop()
    assert sched._running is False
    assert len(sched.workers) == 0


@pytest.mark.asyncio
async def test_scheduler_queue_capacity_limit(temp_scheduler):
    _, db = temp_scheduler
    # Create a scheduler with 0 concurrency so items remain queued without being consumed
    sched = JobScheduler(database=db, max_concurrency=0, max_queue_size=2)
    await sched.start()

    req = ExecutionRequest(language="python", source_code="print(1)", limits=ExecutionLimits())

    # Fill the queue up to max_queue_size (2)
    sched.queue.put_nowait(("dummy_1", req, "usr_dev"))
    sched.queue.put_nowait(("dummy_2", req, "usr_dev"))

    # Next submission must raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        await sched.submit_job(req, user_id="usr_dev")
    assert "queue is full" in str(exc_info.value).lower()
    await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_cancel_pending_job(temp_scheduler):
    sched, db = temp_scheduler
    req = ExecutionRequest(language="python", source_code="print(1)", limits=ExecutionLimits())

    exec_id = await sched.submit_job(req, user_id="usr_tenant_a")
    # Cancel immediately
    cancelled = await sched.cancel_job(exec_id, requesting_user_id="usr_tenant_a")
    assert cancelled is True

    record = await db.get_execution(exec_id)
    assert record["status"] in ("CANCELLED", "FAILED")


@pytest.mark.asyncio
async def test_scheduler_cancel_authorization_rejection(temp_scheduler):
    sched, db = temp_scheduler
    req = ExecutionRequest(language="python", source_code="print(1)", limits=ExecutionLimits())

    exec_id = await sched.submit_job(req, user_id="usr_tenant_a")
    # Tenant B tries to cancel Tenant A's job -> should return False
    cancelled = await sched.cancel_job(exec_id, requesting_user_id="usr_tenant_b")
    assert cancelled is False


@pytest.mark.asyncio
async def test_scheduler_cancel_admin_override(temp_scheduler):
    sched, db = temp_scheduler
    req = ExecutionRequest(language="python", source_code="print(1)", limits=ExecutionLimits())

    exec_id = await sched.submit_job(req, user_id="usr_tenant_a")
    # Admin cancels Tenant A's job -> should succeed
    cancelled = await sched.cancel_job(exec_id, requesting_user_id="usr_admin")
    assert cancelled is True


@pytest.mark.asyncio
async def test_scheduler_cancel_nonexistent(temp_scheduler):
    sched, _ = temp_scheduler
    cancelled = await sched.cancel_job("nonexistent_id", requesting_user_id="usr_admin")
    assert cancelled is False


@pytest.mark.asyncio
async def test_scheduler_runtime_exception_handled_cleanly(temp_scheduler):
    sched, db = temp_scheduler

    # Mock runtime to raise an exception
    mock_runtime = AsyncMock()
    mock_runtime.execute.side_effect = RuntimeError("Sandbox hardware error")

    with patch("api.scheduler.scheduler.get_runtime", return_value=mock_runtime):
        req = ExecutionRequest(language="python", source_code="print(1)", limits=ExecutionLimits())
        exec_id = await sched.submit_job(req, user_id="usr_dev")

        # Wait for worker to process
        for _ in range(50):
            record = await db.get_execution(exec_id)
            if record and record["status"] in ("FAILED", "COMPLETED"):
                break
            await asyncio.sleep(0.05)

        assert record is not None
        assert record["status"] == "FAILED"
        assert "Runtime exception" in record["error_message"]


@pytest.mark.asyncio
async def test_scheduler_successful_job_execution(temp_scheduler):
    sched, db = temp_scheduler

    mock_runtime = AsyncMock()
    mock_runtime.execute.return_value = ExecutionResponse(
        execution_id="mock_id",
        status="completed",
        exit_code=0,
        stdout="Output from worker",
        stderr="",
        termination_reason="normal",
        resource_usage=ResourceUsage(
            wall_time_ms=50, cpu_time_ms=30, memory_peak_bytes=1048576, pids_peak=1
        ),
    )

    with patch("api.scheduler.scheduler.get_runtime", return_value=mock_runtime):
        req = ExecutionRequest(
            language="python", source_code="print('worker')", limits=ExecutionLimits()
        )
        exec_id = await sched.submit_job(req, user_id="usr_dev")

        for _ in range(50):
            record = await db.get_execution(exec_id)
            if record and record["status"] == "COMPLETED":
                break
            await asyncio.sleep(0.05)

        assert record is not None
        assert record["status"] == "COMPLETED"
        assert record["stdout"] == "Output from worker"
        assert record["wall_time_ms"] == 50


@pytest.mark.asyncio
async def test_scheduler_timed_out_status_mapping(temp_scheduler):
    sched, db = temp_scheduler

    mock_runtime = AsyncMock()
    mock_runtime.execute.return_value = ExecutionResponse(
        execution_id="mock_timeout",
        status="timed_out",
        exit_code=-1,
        stdout="",
        stderr="Time limit exceeded",
        termination_reason="timeout",
        resource_usage=ResourceUsage(
            wall_time_ms=5000, cpu_time_ms=4900, memory_peak_bytes=2048576, pids_peak=1
        ),
    )

    with patch("api.scheduler.scheduler.get_runtime", return_value=mock_runtime):
        req = ExecutionRequest(
            language="python", source_code="while True: pass", limits=ExecutionLimits()
        )
        exec_id = await sched.submit_job(req)

        for _ in range(50):
            record = await db.get_execution(exec_id)
            if record and record["status"] in ("TIMED_OUT", "COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.05)

        assert record["status"] == "TIMED_OUT"
        assert record["termination_reason"] == "timeout"


@pytest.mark.asyncio
async def test_scheduler_resource_exceeded_status_mapping(temp_scheduler):
    sched, db = temp_scheduler

    mock_runtime = AsyncMock()
    mock_runtime.execute.return_value = ExecutionResponse(
        execution_id="mock_oom",
        status="resource_limit_exceeded",
        exit_code=-9,
        stdout="",
        stderr="OOM Killed",
        termination_reason="cgroup_oom",
        resource_usage=ResourceUsage(
            wall_time_ms=100, cpu_time_ms=80, memory_peak_bytes=134217728, pids_peak=2
        ),
    )

    with patch("api.scheduler.scheduler.get_runtime", return_value=mock_runtime):
        req = ExecutionRequest(
            language="python", source_code="[1]*9999999", limits=ExecutionLimits()
        )
        exec_id = await sched.submit_job(req)

        for _ in range(50):
            record = await db.get_execution(exec_id)
            if record and record["status"] in ("RESOURCE_LIMIT_EXCEEDED", "FAILED", "COMPLETED"):
                break
            await asyncio.sleep(0.05)

        assert record["status"] == "RESOURCE_LIMIT_EXCEEDED"
        assert record["termination_reason"] == "cgroup_oom"
