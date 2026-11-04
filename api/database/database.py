import asyncio
import atexit
import contextlib
import logging
import os
import weakref
from datetime import UTC, datetime
from typing import Any

import aiosqlite

logger = logging.getLogger("runbox.database")

DB_PATH = os.environ.get(
    "RUNBOX_DB_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "runbox.db")),
)

# Strong set for open connections so they are never garbage collected before cleanup
_open_databases: set["Database"] = set()
# Weak set for all instantiated databases
_all_databases: weakref.WeakSet["Database"] = weakref.WeakSet()
# Backward-compatibility alias
_active_databases = _all_databases


def _cleanup_all_databases() -> None:
    # 1. Clean up strongly tracked open databases first
    for db_instance in list(_open_databases):
        with contextlib.suppress(Exception):
            db_instance.stop_sync()
    # 2. Clean up any remaining instances in weak registry
    for db_instance in list(_all_databases):
        with contextlib.suppress(Exception):
            db_instance.stop_sync()


atexit.register(_cleanup_all_databases)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock: asyncio.Lock | None = None
        self._close_task: asyncio.Task | None = None
        self._last_close_error: Exception | None = None
        self._closed: bool = False
        _all_databases.add(self)

    def _get_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and getattr(self._lock, "_loop", None) is not loop):
            self._lock = asyncio.Lock()
        return self._lock

    def __del__(self) -> None:
        if self._conn is not None:
            self.stop_sync()

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def connect(self):
        lock = self._get_lock()
        async with lock:
            if self._conn is not None:
                return

            self._closed = False
            conn = await aiosqlite.connect(self.db_path)
            try:
                conn.row_factory = aiosqlite.Row
                # Enable Write-Ahead Logging (WAL) for high concurrency
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                await conn.execute("PRAGMA temp_store=MEMORY;")
                await conn.execute("PRAGMA mmap_size=268435456;")
                await conn.execute("PRAGMA cache_size=-64000;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                self._conn = conn
                _open_databases.add(self)
                await self.create_tables()
            except Exception as exc:
                self._conn = None
                _open_databases.discard(self)
                logger.error("Database connection initialization failed: %s", exc)
                with contextlib.suppress(Exception):
                    await conn.close()
                raise

    async def _ensure_connected(self):
        if self._conn is None:
            await self.connect()

    async def close(self) -> None:
        lock = self._get_lock()
        async with lock:
            self._closed = True
            if self._conn is None:
                if self._close_task is not None and not self._close_task.done():
                    # Wait for in-flight close operation to finish
                    await asyncio.shield(self._close_task)
                return

            conn = self._conn
            self._conn = None
            _open_databases.discard(self)
            _all_databases.discard(self)

            async def _do_close():
                try:
                    await conn.close()
                except Exception as exc:
                    self._last_close_error = exc
                    logger.warning("Database close encountered exception: %s", exc)
                    raise
                finally:
                    # Defensive worker thread termination if thread remains alive
                    if hasattr(conn, "_thread") and conn._thread and conn._thread.is_alive():
                        conn._thread.join(timeout=1.0)

            self._close_task = asyncio.create_task(_do_close())

        try:
            await asyncio.shield(self._close_task)
        finally:
            if self._close_task and self._close_task.done():
                self._close_task = None

    def stop_sync(self) -> None:
        """Synchronously stop the aiosqlite worker thread to avoid interpreter hanging at exit."""
        self._closed = True
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            _open_databases.discard(self)
            _all_databases.discard(self)
            try:
                # 1. If an event loop is available and non-active, run loop complete:
                try:
                    loop = asyncio.get_event_loop_policy().get_event_loop()
                    if loop and not loop.is_closed() and not loop.is_running():
                        loop.run_until_complete(conn.close())
                        return
                except Exception:
                    pass

                # 2. Defensive stop sentinel to worker thread queue
                if hasattr(conn, "stop") and callable(conn.stop):
                    conn.stop()

                # 3. Explicit join on the underlying worker thread
                if hasattr(conn, "_thread") and conn._thread and conn._thread.is_alive():
                    conn._thread.join(timeout=1.0)
            except Exception as exc:
                self._last_close_error = exc
                logger.warning("Database stop_sync encountered exception: %s", exc)

    async def create_tables(self):
        query = """
        CREATE TABLE IF NOT EXISTS executions (
            execution_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'usr_dev',
            submitted_at TEXT NOT NULL,
            language TEXT NOT NULL,
            status TEXT NOT NULL,
            exit_code INTEGER,
            termination_reason TEXT,
            stdout TEXT,
            stderr TEXT,
            source_code TEXT,
            wall_time_ms INTEGER DEFAULT 0,
            cpu_time_ms INTEGER DEFAULT 0,
            memory_peak_bytes INTEGER DEFAULT 0,
            pids_peak INTEGER DEFAULT 0,
            compilation_duration_ms INTEGER,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_executions_submitted ON executions(submitted_at);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
        CREATE INDEX IF NOT EXISTS idx_executions_user ON executions(user_id);
        """
        await self._conn.executescript(query)

        # Migration check: Ensure user_id column exists if table was previously created without it
        try:
            async with self._conn.execute("PRAGMA table_info(executions)") as cursor:
                columns = [row["name"] for row in await cursor.fetchall()]
                if "user_id" not in columns:
                    await self._conn.execute(
                        "ALTER TABLE executions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'usr_dev';"
                    )
        except Exception:
            pass

        await self._conn.commit()

    async def recover_stale_executions(self) -> int:
        """
        On service startup, reset any executions left in transitional states
        due to sudden service restarts or power interruptions.
        """
        await self._ensure_connected()
        query = """
        UPDATE executions
        SET status = 'FAILED',
            termination_reason = 'server_restarted',
            error_message = 'Interrupted by server reboot or ungraceful shutdown'
        WHERE status IN ('QUEUED', 'INITIALIZING', 'RUNNING');
        """
        cursor = await self._conn.execute(query)
        await self._conn.commit()
        return cursor.rowcount

    async def record_submission(
        self,
        execution_id: str,
        language: str,
        source_code: str | None = None,
        user_id: str = "usr_dev",
    ):
        await self._ensure_connected()
        now = datetime.now(UTC).isoformat()
        query = """
        INSERT INTO executions (
            execution_id, user_id, submitted_at, language, status, source_code
        ) VALUES (?, ?, ?, ?, 'QUEUED', ?)
        """
        await self._conn.execute(query, (execution_id, user_id, now, language, source_code))
        await self._conn.commit()

    async def update_status(self, execution_id: str, status: str, error_message: str | None = None):
        await self._ensure_connected()
        query = "UPDATE executions SET status = ?, error_message = COALESCE(?, error_message) WHERE execution_id = ?"
        await self._conn.execute(query, (status, error_message, execution_id))
        await self._conn.commit()

    async def record_result(
        self,
        execution_id: str,
        status: str,
        exit_code: int,
        termination_reason: str,
        stdout: str,
        stderr: str,
        wall_time_ms: int,
        cpu_time_ms: int,
        memory_peak_bytes: int,
        pids_peak: int,
        compilation_duration_ms: int | None = None,
        error_message: str | None = None,
    ):
        await self._ensure_connected()
        query = """
        UPDATE executions SET
            status = ?,
            exit_code = ?,
            termination_reason = ?,
            stdout = ?,
            stderr = ?,
            wall_time_ms = ?,
            cpu_time_ms = ?,
            memory_peak_bytes = ?,
            pids_peak = ?,
            compilation_duration_ms = ?,
            error_message = ?
        WHERE execution_id = ?
        """
        await self._conn.execute(
            query,
            (
                status,
                exit_code,
                termination_reason,
                stdout,
                stderr,
                wall_time_ms,
                cpu_time_ms,
                memory_peak_bytes,
                pids_peak,
                compilation_duration_ms,
                error_message,
                execution_id,
            ),
        )
        await self._conn.commit()

    async def get_execution(
        self, execution_id: str, user_id: str | None = None
    ) -> dict[str, Any] | None:
        await self._ensure_connected()
        if user_id and user_id != "usr_admin":
            query = "SELECT * FROM executions WHERE execution_id = ? AND user_id = ?"
            params = (execution_id, user_id)
        else:
            query = "SELECT * FROM executions WHERE execution_id = ?"
            params = (execution_id,)

        async with self._conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def list_executions(
        self, user_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        await self._ensure_connected()
        if user_id and user_id != "usr_admin":
            query = "SELECT * FROM executions WHERE user_id = ? ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
            params = (user_id, limit, offset)
        else:
            query = "SELECT * FROM executions ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
            params = (limit, offset)

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def purge_old_executions(self, retention_days: int = 30) -> int:
        await self._ensure_connected()
        cutoff_date = datetime.now(UTC).timestamp() - (retention_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff_date, tz=UTC).isoformat()
        cursor = await self._conn.execute(
            "DELETE FROM executions WHERE submitted_at < ?", (cutoff_iso,)
        )
        await self._conn.commit()
        return cursor.rowcount

    async def get_metrics(self) -> dict[str, Any]:
        await self._ensure_connected()
        query = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'TIMED_OUT' THEN 1 ELSE 0 END) as timed_out,
            SUM(CASE WHEN status = 'RESOURCE_LIMIT_EXCEEDED' THEN 1 ELSE 0 END) as resource_exceeded,
            SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
            AVG(wall_time_ms) as avg_wall_time_ms,
            AVG(cpu_time_ms) as avg_cpu_time_ms
        FROM executions
        """
        async with self._conn.execute(query) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                return {k: (v if v is not None else 0) for k, v in d.items()}
        return {}
