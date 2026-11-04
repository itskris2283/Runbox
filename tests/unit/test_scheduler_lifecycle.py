import asyncio
import os
import tempfile

import pytest

from api.database.database import Database
from api.scheduler.scheduler import JobScheduler
from runtimes.base import ExecutionLimits, ExecutionRequest


@pytest.fixture
async def temp_env():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_file = tf.name
    db = Database(db_file)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.mark.asyncio
async def test_scheduler_normal_shutdown(temp_env):
    """Verify normal startup and clean shutdown of worker pool."""
    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=4, max_queue_size=10)
    await sched.start()
    assert sched._running is True
    assert len(sched.workers) == 4

    await sched.stop()
    assert sched._running is False
    assert len(sched.workers) == 0
    assert len(sched.active_tasks) == 0


@pytest.mark.asyncio
async def test_scheduler_shutdown_with_queued_jobs(temp_env):
    """Verify shutdown with queued jobs drains the queue and marks jobs CANCELLED."""
    db = temp_env
    # Concurrency 0 means workers won't consume items from the queue
    sched = JobScheduler(database=db, max_concurrency=0, max_queue_size=10)
    await sched.start()

    req = ExecutionRequest(
        language="python", source_code="print('queued')", limits=ExecutionLimits()
    )
    exec_id_1 = await sched.submit_job(req, user_id="usr_a")
    exec_id_2 = await sched.submit_job(req, user_id="usr_b")

    assert sched.queue.qsize() == 2

    # Stop scheduler while items are queued
    await sched.stop()
    assert sched._running is False
    assert sched.queue.empty()

    # Verify both jobs were marked CANCELLED in DB
    rec1 = await db.get_execution(exec_id_1)
    rec2 = await db.get_execution(exec_id_2)
    assert rec1["status"] in ("CANCELLED", "FAILED")
    assert rec2["status"] in ("CANCELLED", "FAILED")


@pytest.mark.asyncio
async def test_scheduler_shutdown_with_active_jobs(temp_env):
    """Verify shutdown while jobs are actively executing cancels them cleanly."""
    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    await sched.start()

    # Submit a job that sleeps for 5 seconds
    req = ExecutionRequest(
        language="python",
        source_code="import time; time.sleep(5)",
        limits=ExecutionLimits(timeout_ms=5000),
    )
    exec_id = await sched.submit_job(req)

    # Wait until job enters active execution
    for _ in range(40):
        rec = await db.get_execution(exec_id)
        if rec and rec["status"] == "RUNNING":
            break
        await asyncio.sleep(0.05)

    # Stop scheduler while job is running
    await sched.stop()
    assert sched._running is False
    assert len(sched.active_tasks) == 0

    rec = await db.get_execution(exec_id)
    assert rec["status"] in ("CANCELLED", "FAILED")


@pytest.mark.asyncio
async def test_scheduler_repeated_shutdown_is_idempotent(temp_env):
    """Verify calling stop repeatedly or stop_sync after stop causes no errors."""
    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    await sched.start()

    # 1st stop
    await sched.stop()
    assert sched._running is False

    # 2nd stop
    await sched.stop()
    assert sched._running is False

    # 3rd stop_sync
    sched.stop_sync()
    assert sched._running is False


@pytest.mark.asyncio
async def test_scheduler_restart_after_shutdown(temp_env):
    """Verify scheduler can be restarted cleanly after being stopped."""
    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    await sched.start()
    await sched.stop()
    assert sched._running is False

    # Restart
    await sched.start()
    assert sched._running is True
    assert len(sched.workers) == 2

    # Execute a job on restarted scheduler
    req = ExecutionRequest(
        language="python",
        source_code="print('restarted_ok')",
        limits=ExecutionLimits(timeout_ms=2000),
    )
    exec_id = await sched.submit_job(req)

    for _ in range(50):
        rec = await db.get_execution(exec_id)
        if rec and rec["status"] in ("COMPLETED", "FAILED"):
            break
        await asyncio.sleep(0.05)

    assert rec["status"] == "COMPLETED"
    assert "restarted_ok" in rec["stdout"]

    await sched.stop()


@pytest.mark.asyncio
async def test_multiple_scheduler_instances(temp_env):
    """Verify multiple independent schedulers do not interfere with each other."""
    db = temp_env
    sched1 = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    sched2 = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)

    await sched1.start()
    await sched2.start()

    assert sched1._running is True
    assert sched2._running is True

    await sched1.stop()
    assert sched1._running is False
    assert sched2._running is True

    await sched2.stop()
    assert sched2._running is False


@pytest.mark.asyncio
async def test_stop_sync_cancels_all_worker_tasks(temp_env):
    """Verify stop_sync cancels all worker tasks immediately."""
    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=3, max_queue_size=5)
    await sched.start()
    assert len(sched.workers) == 3

    sched.stop_sync()
    assert sched._running is False
    assert len(sched.workers) == 0


@pytest.mark.asyncio
async def test_quota_invariant_completed_and_failed_jobs(temp_env):
    """Verify completed and failed executions release tenant quota slots exactly once."""
    from api.security.auth import AuthenticatedUser
    from api.security.quotas import quota_manager

    db = temp_env
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    await sched.start()

    user = AuthenticatedUser(
        user_id="usr_quota_test", username="qtester", role="user", max_concurrency=3
    )
    quota_manager.acquire_slot(user)
    assert quota_manager.get_active_count("usr_quota_test") == 1

    req = ExecutionRequest(
        language="python", source_code="print('quota_check')", limits=ExecutionLimits()
    )
    exec_id = await sched.submit_job(req, user_id="usr_quota_test")
    quota_manager.register_execution(exec_id, "usr_quota_test")

    for _ in range(50):
        rec = await db.get_execution(exec_id)
        if rec and rec["status"] in ("COMPLETED", "FAILED"):
            break
        await asyncio.sleep(0.05)

    assert rec["status"] == "COMPLETED"
    # Allow worker loop finally block to execute
    await asyncio.sleep(0.05)
    assert quota_manager.get_active_count("usr_quota_test") == 0

    await sched.stop()


@pytest.mark.asyncio
async def test_quota_invariant_cancelled_queued_job(temp_env):
    """Verify cancelled queued job releases its quota slot without double-release."""
    from api.security.auth import AuthenticatedUser
    from api.security.quotas import quota_manager

    db = temp_env
    # 0 workers keeps job queued
    sched = JobScheduler(database=db, max_concurrency=0, max_queue_size=5)
    await sched.start()

    user = AuthenticatedUser(
        user_id="usr_cancel_test", username="ctester", role="user", max_concurrency=2
    )
    quota_manager.acquire_slot(user)
    assert quota_manager.get_active_count("usr_cancel_test") == 1

    req = ExecutionRequest(
        language="python", source_code="print('will_cancel')", limits=ExecutionLimits()
    )
    exec_id = await sched.submit_job(req, user_id="usr_cancel_test")
    quota_manager.register_execution(exec_id, "usr_cancel_test")

    # Cancel the queued job
    success = await sched.cancel_job(exec_id, requesting_user_id="usr_cancel_test")
    assert success is True
    assert quota_manager.get_active_count("usr_cancel_test") == 0

    # Verify repeated cancellation does not decrement below zero or double-release
    success_again = await sched.cancel_job(exec_id, requesting_user_id="usr_cancel_test")
    assert success_again is False
    assert quota_manager.get_active_count("usr_cancel_test") == 0

    await sched.stop()


@pytest.mark.asyncio
async def test_quota_double_release_prevention():
    """Verify exactly-once slot release semantics prevent double release across multiple callers."""
    from api.security.auth import AuthenticatedUser
    from api.security.quotas import quota_manager

    user = AuthenticatedUser(
        user_id="usr_double_rel", username="dtester", role="user", max_concurrency=5
    )
    quota_manager.acquire_slot(user)
    assert quota_manager.get_active_count("usr_double_rel") == 1

    exec_id = "job-double-release-1"
    quota_manager.register_execution(exec_id, "usr_double_rel")

    # First release succeeds and decrements
    first_release = quota_manager.release_slot("usr_double_rel", execution_id=exec_id)
    assert first_release is True
    assert quota_manager.get_active_count("usr_double_rel") == 0

    # Second release is an idempotent no-op
    second_release = quota_manager.release_slot("usr_double_rel", execution_id=exec_id)
    assert second_release is False
    assert quota_manager.get_active_count("usr_double_rel") == 0


@pytest.mark.asyncio
async def test_quota_cross_tenant_isolation():
    """Verify Tenant A's quota exhaustion does not affect Tenant B."""
    from api.security.auth import AuthenticatedUser
    from api.security.quotas import quota_manager

    tenant_a = AuthenticatedUser(user_id="usr_t_a", username="t_a", role="user", max_concurrency=2)
    tenant_b = AuthenticatedUser(user_id="usr_t_b", username="t_b", role="user", max_concurrency=2)

    # Exhaust tenant A quota
    quota_manager.acquire_slot(tenant_a, execution_id="job_a_1")
    quota_manager.acquire_slot(tenant_a, execution_id="job_a_2")
    assert quota_manager.get_active_count("usr_t_a") == 2

    # Tenant B should still be able to acquire slots freely
    quota_manager.acquire_slot(tenant_b, execution_id="job_b_1")
    assert quota_manager.get_active_count("usr_t_b") == 1

    # Cleanup
    quota_manager.release_slot("usr_t_a", execution_id="job_a_1")
    quota_manager.release_slot("usr_t_a", execution_id="job_a_2")
    quota_manager.release_slot("usr_t_b", execution_id="job_b_1")
    assert quota_manager.get_active_count("usr_t_a") == 0
    assert quota_manager.get_active_count("usr_t_b") == 0
