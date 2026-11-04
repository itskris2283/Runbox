import os
import tempfile

import pytest

from api.database.database import Database


@pytest.mark.asyncio
async def test_database_crud():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    db = Database(temp_db)
    await db.connect()

    try:
        # 1. Submission
        await db.record_submission("job-test-1", "python", "print('hello')")
        record = await db.get_execution("job-test-1")
        assert record is not None
        assert record["status"] == "QUEUED"
        assert record["language"] == "python"

        # 2. Status update
        await db.update_status("job-test-1", "RUNNING")
        record = await db.get_execution("job-test-1")
        assert record["status"] == "RUNNING"

        # 3. Result update
        await db.record_result(
            execution_id="job-test-1",
            status="COMPLETED",
            exit_code=0,
            termination_reason="normal_exit",
            stdout="hello\n",
            stderr="",
            wall_time_ms=45,
            cpu_time_ms=12,
            memory_peak_bytes=1048576,
            pids_peak=1,
        )

        record = await db.get_execution("job-test-1")
        assert record["status"] == "COMPLETED"
        assert record["exit_code"] == 0
        assert record["stdout"] == "hello\n"
        assert record["wall_time_ms"] == 45

        # 4. Metrics
        metrics = await db.get_metrics()
        assert metrics["total"] == 1
        assert metrics["completed"] == 1
        assert metrics["failed"] == 0
    finally:
        await db.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)
