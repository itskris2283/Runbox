import asyncio
import os
import tempfile

import pytest

from api.database.database import Database
from api.scheduler.scheduler import JobScheduler
from runtimes.base import ExecutionLimits, ExecutionRequest


@pytest.mark.asyncio
async def test_scheduler_queue_and_concurrency():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    db = Database(temp_db)
    await db.connect()
    sched = JobScheduler(database=db, max_concurrency=2, max_queue_size=5)
    await sched.start()

    try:
        req = ExecutionRequest(
            language="python",
            source_code="print('scheduler test')",
            limits=ExecutionLimits(timeout_ms=1000),
        )
        job_id = await sched.submit_job(req)
        assert job_id.startswith("job-")

        # Wait briefly for execution to complete
        for _ in range(50):
            job = await db.get_execution(job_id)
            if job and job["status"] in ("COMPLETED", "FAILED", "TIMED_OUT"):
                break
            await asyncio.sleep(0.05)

        assert job["status"] == "COMPLETED"
        assert "scheduler test" in job["stdout"]
    finally:
        await sched.stop()
        await db.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)
