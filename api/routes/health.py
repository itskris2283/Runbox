import os

from fastapi import APIRouter

from api.database.database import Database
from api.scheduler.scheduler import JobScheduler

router = APIRouter(tags=["Health & Telemetry"])

db: Database = None  # type: ignore
scheduler: JobScheduler = None  # type: ignore


def init_dependencies(database: Database, job_scheduler: JobScheduler):
    global db, scheduler
    db = database
    scheduler = job_scheduler


@router.get("/healthz")
@router.get("/health")
@router.get("/api/v1/health/live")
async def liveness():
    return {"status": "ok", "service": "runbox-api", "version": "0.1.1"}


@router.get("/readyz")
@router.get("/api/v1/health/ready")
async def readiness():
    from runtimes.supervisor_invoker import SUPERVISOR_PATH

    supervisor_ready = os.path.exists(SUPERVISOR_PATH) and os.access(SUPERVISOR_PATH, os.X_OK)
    cgroup_ready = os.path.exists("/sys/fs/cgroup")

    return {
        "status": "ready" if (supervisor_ready and cgroup_ready) else "degraded",
        "supervisor_binary": supervisor_ready,
        "cgroup_v2": cgroup_ready,
        "active_workers": len(scheduler.active_tasks),
        "queue_depth": scheduler.queue.qsize(),
    }


@router.get("/api/v1/metrics")
async def metrics():
    stats = await db.get_metrics()
    return {
        "executions": stats,
        "active_jobs": len(scheduler.active_tasks),
        "queue_size": scheduler.queue.qsize(),
        "max_concurrency": scheduler.max_concurrency,
    }
