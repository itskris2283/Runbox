import asyncio
import atexit
import contextlib
import os
import shutil
import uuid
import weakref
from typing import Any

from api.database.database import Database
from api.security.quotas import quota_manager
from runtimes import get_runtime
from runtimes.base import ExecutionRequest, ExecutionResponse
from runtimes.supervisor_invoker import kill_active_process, kill_all_active_processes

_active_schedulers: weakref.WeakSet["JobScheduler"] = weakref.WeakSet()


def _cleanup_all_schedulers() -> None:
    for sched in list(_active_schedulers):
        with contextlib.suppress(Exception):
            sched.stop_sync()


atexit.register(_cleanup_all_schedulers)


class JobScheduler:
    def __init__(self, database: Database, max_concurrency: int = 20, max_queue_size: int = 200):
        self.db = database
        self.max_concurrency = max_concurrency
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.cancelled_jobs: set[str] = set()
        self.workers: list[asyncio.Task] = []
        self._running = False
        _active_schedulers.add(self)

    async def start(self):
        if self._running:
            return
        self._running = True
        self.workers.clear()
        for i in range(self.max_concurrency):
            task = asyncio.create_task(self._worker_loop(i), name=f"runbox-worker-{i}")
            self.workers.append(task)

    async def stop(self):
        self._running = False
        # Kill all running supervisor processes
        kill_all_active_processes()

        # Cancel all actively executing jobs
        for task in list(self.active_tasks.values()):
            task.cancel()

        # Cancel all worker tasks
        for task in self.workers:
            task.cancel()

        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        self.active_tasks.clear()

        # Drain any remaining queued items and assign terminal status
        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                if len(item) == 3:
                    execution_id, _, user_id = item
                else:
                    execution_id, _ = item
                    user_id = "usr_dev"
                quota_manager.release_slot(user_id, execution_id=execution_id)
                self.queue.task_done()
                with contextlib.suppress(Exception):
                    await self.db.update_status(
                        execution_id, "CANCELLED", "Cancelled during scheduler shutdown"
                    )
            except (asyncio.QueueEmpty, ValueError):
                break

        _active_schedulers.discard(self)

    def stop_sync(self):
        """Synchronous cleanup to cancel tasks without awaiting on interpreter shutdown."""
        self._running = False
        kill_all_active_processes()
        for task in list(self.active_tasks.values()):
            with contextlib.suppress(Exception):
                task.cancel()
        for task in list(self.workers):
            with contextlib.suppress(Exception):
                task.cancel()
        self.workers.clear()
        self.active_tasks.clear()
        _active_schedulers.discard(self)

    async def submit_job(self, request: ExecutionRequest, user_id: str = "usr_dev") -> str:
        if not self._running:
            await self.start()

        execution_id = f"job-{uuid.uuid4().hex[:12]}"
        await self.db.record_submission(
            execution_id, request.language, request.source_code, user_id=user_id
        )

        try:
            self.queue.put_nowait((execution_id, request, user_id))
        except asyncio.QueueFull:
            quota_manager.release_slot(user_id, execution_id=execution_id)
            await self.db.update_status(execution_id, "REJECTED", "Queue capacity exceeded")
            raise RuntimeError("Execution queue is full. Try again later.") from None

        return execution_id

    async def cancel_job(self, execution_id: str, requesting_user_id: str | None = None) -> bool:
        job = await self.db.get_execution(execution_id)
        if not job:
            return False

        # Authorization ownership check
        if (
            requesting_user_id
            and requesting_user_id != "usr_admin"
            and job.get("user_id") != requesting_user_id
        ):
            return False

        self.cancelled_jobs.add(execution_id)
        owner_id = job.get("user_id", "usr_dev")
        quota_manager.release_slot(owner_id, execution_id=execution_id)

        # Force terminate underlying supervisor process immediately
        kill_active_process(execution_id)

        if execution_id in self.active_tasks:
            self.active_tasks[execution_id].cancel()
            await self.db.update_status(execution_id, "CANCELLED", "User requested cancellation")
            return True

        if job["status"] in ("QUEUED", "INITIALIZING"):
            await self.db.update_status(execution_id, "CANCELLED", "Cancelled while queued")
            return True

        return False

    async def _worker_loop(self, worker_id: int):
        while self._running:
            try:
                item: Any = await self.queue.get()
            except asyncio.CancelledError:
                break

            # Handle both 2-tuple and 3-tuple queue items for backward compatibility
            if len(item) == 3:
                execution_id, request, user_id = item
            else:
                execution_id, request = item
                user_id = "usr_dev"

            if execution_id in self.cancelled_jobs:
                self.cancelled_jobs.remove(execution_id)
                quota_manager.release_slot(user_id, execution_id=execution_id)
                self.queue.task_done()
                continue

            current_task = asyncio.current_task()
            if current_task:
                self.active_tasks[execution_id] = current_task

            if execution_id in self.cancelled_jobs:
                self.cancelled_jobs.remove(execution_id)
                self.active_tasks.pop(execution_id, None)
                quota_manager.release_slot(user_id, execution_id=execution_id)
                self.queue.task_done()
                continue

            workspace_dir = f"/tmp/runbox_ws_{execution_id}"
            os.makedirs(workspace_dir, exist_ok=True)

            try:
                runtime = get_runtime(request.language)
                await self.db.update_status(execution_id, "RUNNING")
                response: ExecutionResponse = await runtime.execute(
                    execution_id, request, workspace_dir
                )

                db_status = "COMPLETED"
                if response.status == "timed_out":
                    db_status = "TIMED_OUT"
                elif response.status == "resource_limit_exceeded":
                    db_status = "RESOURCE_LIMIT_EXCEEDED"
                elif response.exit_code != 0:
                    db_status = "FAILED"

                if os.path.exists(workspace_dir):
                    await asyncio.to_thread(shutil.rmtree, workspace_dir, ignore_errors=True)

                await self.db.record_result(
                    execution_id=execution_id,
                    status=db_status,
                    exit_code=response.exit_code,
                    termination_reason=response.termination_reason,
                    stdout=response.stdout,
                    stderr=response.stderr,
                    wall_time_ms=response.resource_usage.wall_time_ms,
                    cpu_time_ms=response.resource_usage.cpu_time_ms,
                    memory_peak_bytes=response.resource_usage.memory_peak_bytes,
                    pids_peak=response.resource_usage.pids_peak,
                    compilation_duration_ms=getattr(response, "compilation_duration_ms", None),
                    error_message=response.stderr
                    if response.exit_code != 0 and not response.stdout
                    else None,
                )

            except asyncio.CancelledError:
                await self.db.update_status(
                    execution_id, "CANCELLED", "Execution cancelled by user"
                )
            except Exception as e:
                await self.db.update_status(execution_id, "FAILED", f"Runtime exception: {e}")
            finally:
                self.active_tasks.pop(execution_id, None)
                quota_manager.release_slot(user_id, execution_id=execution_id)
                self.queue.task_done()
                if os.path.exists(workspace_dir):
                    await asyncio.to_thread(shutil.rmtree, workspace_dir, ignore_errors=True)
