import asyncio
import os
import tempfile
import threading
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from api.database.database import Database


def count_aiosqlite_threads():
    return sum(
        1
        for t in threading.enumerate()
        if "aiosqlite" in t.name.lower()
        or (t._target and "worker" in getattr(t._target, "__name__", "").lower())
    )


@pytest.mark.asyncio
async def test_normal_connection_closure():
    """Verify normal connection and clean closure."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()
        assert db._conn is not None

        # Verify query can execute
        await db.record_submission("job-life-1", "python", "print(1)")
        rec = await db.get_execution("job-life-1")
        assert rec is not None

        # Clean closure
        await db.close()
        assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_repeated_closure_is_idempotent():
    """Verify calling close multiple times or mixing close and stop_sync is completely safe."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()
        assert db._conn is not None

        # 1st close
        await db.close()
        assert db._conn is None

        # 2nd close - should be a safe no-op
        await db.close()
        assert db._conn is None

        # 3rd: stop_sync - should also be a safe no-op
        db.stop_sync()
        assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_concurrent_calls_to_close():
    """Verify two or more simultaneous calls to close() behave deterministically without race conditions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()
        assert db._conn is not None

        # Execute concurrent close calls
        results = await asyncio.gather(
            db.close(),
            db.close(),
            db.close(),
            return_exceptions=True,
        )

        for res in results:
            assert not isinstance(res, Exception)
        assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_cancellation_during_close_is_shielded():
    """Verify that cancelling the coroutine awaiting close() does not abandon thread cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()
        conn_ref = db._conn
        assert conn_ref is not None

        # Start close task and cancel it immediately
        task = asyncio.create_task(db.close())
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Allow shielded close task a tick to complete
        await asyncio.sleep(0.05)

        # Ensure the connection was marked closed and worker thread joined
        assert db._conn is None
        if hasattr(conn_ref, "_thread") and conn_ref._thread:
            assert not conn_ref._thread.is_alive()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_closure_during_active_database_operation():
    """Verify closing while queries are executing handles operations without hanging."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()

        # Launch concurrent submissions and immediately initiate close
        async def submit_batch():
            for i in range(10):
                if db._closed:
                    break
                try:
                    await db.record_submission(f"job-active-{i}", "python", "print(1)")
                except Exception:
                    break

        batch_task = asyncio.create_task(submit_batch())
        await asyncio.sleep(0.005)
        await db.close()
        await batch_task

        assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_closure_preserves_error_observability():
    """Verify exceptions during connection close are logged and observable."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()

        # Mock close to raise an OperationalError
        mock_error = aiosqlite.OperationalError("Simulated hardware error on flush")
        with patch.object(db._conn, "close", new=AsyncMock(side_effect=mock_error)):
            with pytest.raises(aiosqlite.OperationalError):
                await db.close()

            assert db._last_close_error is not None
            assert "Simulated hardware error" in str(db._last_close_error)
            assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_unclosed_database_del_cleanup():
    """Verify that garbage collection of an unclosed Database triggers stop_sync cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        initial_threads = count_aiosqlite_threads()
        db = Database(temp_path)
        await db.connect()
        conn_ref = db._conn
        assert conn_ref is not None

        # Simulate dropping the reference without awaiting close()
        # Explicitly call __del__ as Python's GC timing is non-deterministic
        db.__del__()
        await asyncio.sleep(0.05)

        if hasattr(conn_ref, "_thread") and conn_ref._thread:
            assert not conn_ref._thread.is_alive()
        assert count_aiosqlite_threads() <= initial_threads
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_closure_after_initialization_failure():
    """Verify initialization failure leaves no dangling worker thread or open connection."""
    invalid_path = "/nonexistent_invalid_dir_9999/test.db"
    db = Database(invalid_path)

    with pytest.raises((aiosqlite.OperationalError, OSError)):
        await db.connect()

    assert db._conn is None
    # Verify closing uninitialized db is safe
    await db.close()
    db.stop_sync()


@pytest.mark.asyncio
async def test_closure_after_database_exceptions():
    """Verify connection closes cleanly even after SQL query exceptions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db = Database(temp_path)
        await db.connect()

        # Trigger a database syntax error
        with pytest.raises(aiosqlite.OperationalError):
            await db._conn.execute("INVALID SQL STATEMENT SYNTAX ERROR;")

        await asyncio.sleep(0.01)

        # Connection must still close deterministically without deadlock
        await db.close()
        assert db._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_multiple_active_database_instances():
    """Verify multiple independent database instances operate concurrently and close independently."""
    paths = []
    dbs = []
    try:
        for i in range(3):
            with tempfile.NamedTemporaryFile(suffix=f"_inst_{i}.db", delete=False) as tf:
                paths.append(tf.name)
            d = Database(paths[-1])
            await d.connect()
            dbs.append(d)

        for i, d in enumerate(dbs):
            assert d._conn is not None
            await d.record_submission(f"job-multi-{i}", "python", f"print({i})")

        for d in reversed(dbs):
            await d.close()
            assert d._conn is None
    finally:
        for p in paths:
            if os.path.exists(p):
                os.remove(p)


@pytest.mark.asyncio
async def test_async_context_manager_lifecycle():
    """Verify Database async context manager connect/close semantics."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        db_ref = None
        async with Database(temp_path) as db:
            db_ref = db
            assert db._conn is not None
            await db.record_submission("job-cm-1", "python", "print('cm')")
            rec = await db.get_execution("job-cm-1")
            assert rec["execution_id"] == "job-cm-1"

        assert db_ref._conn is None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_no_remaining_aiosqlite_worker_threads():
    """Verify all aiosqlite background worker threads terminate after database close."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = tf.name

    try:
        initial_count = count_aiosqlite_threads()
        db = Database(temp_path)
        await db.connect()
        await db.record_submission("job-thr-1", "python", "print(1)")

        await db.close()
        await asyncio.sleep(0.05)
        final_count = count_aiosqlite_threads()
        assert final_count <= initial_count
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
