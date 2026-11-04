from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.database.database import Database
from api.models.execution import (
    MAX_ALLOWED_CPU_QUOTA,
    MAX_ALLOWED_MEMORY_MB,
    MAX_ALLOWED_OUTPUT_BYTES,
    MAX_ALLOWED_PIDS,
    MAX_ALLOWED_TIMEOUT_MS,
    ExecutionListResponseModel,
    ExecutionRequestModel,
    ExecutionSummaryItem,
    SubmissionResponseModel,
)
from api.scheduler.scheduler import JobScheduler
from api.security.auth import AuthenticatedUser, get_current_user
from api.security.quotas import quota_manager
from api.security.rate_limiter import rate_limiter
from runtimes.base import ExecutionLimits, ExecutionRequest

router = APIRouter(prefix="/api/v1/executions", tags=["Executions"])

# Injected by main.py
db: Database = None  # type: ignore
scheduler: JobScheduler = None  # type: ignore


def init_dependencies(database: Database, job_scheduler: JobScheduler):
    global db, scheduler
    db = database
    scheduler = job_scheduler


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=SubmissionResponseModel)
async def submit_execution(
    request: ExecutionRequestModel, user: AuthenticatedUser = Depends(get_current_user)
):
    lang = request.language.lower().strip()
    if lang not in ("python", "python3", "py", "cpp", "c++", "c"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language: '{request.language}'. Supported: python, cpp.",
        )

    # Enforce per-user sliding window rate limits
    rate_limiter.check_rate_limit(user)

    # Enforce per-user concurrent execution quota
    quota_manager.acquire_slot(user)

    # Defense-in-depth clamping to system maximum thresholds
    clamped_limits = ExecutionLimits(
        timeout_ms=min(request.limits.timeout_ms, MAX_ALLOWED_TIMEOUT_MS),
        memory_mb=min(request.limits.memory_mb, MAX_ALLOWED_MEMORY_MB),
        cpu_quota_percent=min(request.limits.cpu_quota_percent, MAX_ALLOWED_CPU_QUOTA),
        process_limit=min(request.limits.process_limit, MAX_ALLOWED_PIDS),
        output_limit_bytes=min(request.limits.output_limit_bytes, MAX_ALLOWED_OUTPUT_BYTES),
    )

    core_req = ExecutionRequest(
        language=lang, source_code=request.source_code, stdin=request.stdin, limits=clamped_limits
    )

    try:
        execution_id = await scheduler.submit_job(core_req, user_id=user.user_id)
        quota_manager.register_execution(execution_id, user.user_id)
        return {
            "execution_id": execution_id,
            "status": "queued",
            "message": "Job accepted and queued for execution",
        }
    except RuntimeError as e:
        quota_manager.release_slot(user.user_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e


@router.get("/{execution_id}")
async def get_execution_status(
    execution_id: str, user: AuthenticatedUser = Depends(get_current_user)
):
    record = await db.get_execution(execution_id, user_id=user.user_id)
    if not record:
        # Enforce anti-enumeration: return 404 regardless of whether job exists under another tenant
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution '{execution_id}' not found"
        )

    return {
        "execution_id": record["execution_id"],
        "user_id": record.get("user_id", "usr_dev"),
        "status": record["status"].lower(),
        "exit_code": record["exit_code"],
        "stdout": record["stdout"] or "",
        "stderr": record["stderr"] or "",
        "termination_reason": record["termination_reason"] or "pending",
        "compilation_duration_ms": record["compilation_duration_ms"],
        "error_message": record["error_message"],
        "resource_usage": {
            "wall_time_ms": record["wall_time_ms"],
            "cpu_time_ms": record["cpu_time_ms"],
            "memory_peak_bytes": record["memory_peak_bytes"],
            "pids_peak": record["pids_peak"],
        },
    }


@router.delete("/{execution_id}")
async def cancel_execution(execution_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    record = await db.get_execution(execution_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution '{execution_id}' not found"
        )

    # Enforce strict anti-enumeration: return 404 if execution is owned by another tenant
    if user.role != "admin" and record.get("user_id") != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' not found",
        )

    if record["status"] in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
        return {
            "execution_id": execution_id,
            "status": record["status"].lower(),
            "cancelled": False,
        }

    success = await scheduler.cancel_job(execution_id, requesting_user_id=user.user_id)
    return {"execution_id": execution_id, "status": "cancelled", "cancelled": success}


@router.get("", response_model=ExecutionListResponseModel)
async def list_executions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
):
    records = await db.list_executions(user_id=user.user_id, limit=limit, offset=offset)
    return {
        "count": len(records),
        "executions": [
            ExecutionSummaryItem(
                execution_id=r["execution_id"],
                language=r["language"],
                status=r["status"].lower(),
                submitted_at=r["submitted_at"],
                exit_code=r["exit_code"],
                termination_reason=r["termination_reason"],
                wall_time_ms=r["wall_time_ms"],
            )
            for r in records
        ],
    }
