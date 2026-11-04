from typing import Any

from pydantic import BaseModel, Field

# Administrator Hard Caps for Sandbox Configuration
MAX_ALLOWED_TIMEOUT_MS = 30000
MAX_ALLOWED_MEMORY_MB = 1024
MAX_ALLOWED_CPU_QUOTA = 100
MAX_ALLOWED_PIDS = 64
MAX_ALLOWED_OUTPUT_BYTES = 5 * 1024 * 1024
MAX_SOURCE_CODE_BYTES = 65536  # 64 KB code limit
MAX_STDIN_BYTES = 65536  # 64 KB stdin limit


class ExecutionLimitsModel(BaseModel):
    timeout_ms: int = Field(default=3000, ge=10, le=MAX_ALLOWED_TIMEOUT_MS)
    memory_mb: int = Field(default=128, ge=16, le=MAX_ALLOWED_MEMORY_MB)
    cpu_quota_percent: int = Field(default=50, ge=1, le=MAX_ALLOWED_CPU_QUOTA)
    process_limit: int = Field(default=32, ge=1, le=MAX_ALLOWED_PIDS)
    output_limit_bytes: int = Field(default=1048576, ge=1024, le=MAX_ALLOWED_OUTPUT_BYTES)


class ExecutionRequestModel(BaseModel):
    language: str = Field(..., min_length=1, max_length=32)
    source_code: str = Field(..., min_length=1, max_length=MAX_SOURCE_CODE_BYTES)
    stdin: str = Field(default="", max_length=MAX_STDIN_BYTES)
    limits: ExecutionLimitsModel = Field(default_factory=ExecutionLimitsModel)


class SubmissionResponseModel(BaseModel):
    execution_id: str
    status: str
    message: str


class ResourceUsageModel(BaseModel):
    wall_time_ms: int = 0
    cpu_time_ms: int = 0
    memory_peak_bytes: int = 0
    pids_peak: int = 0


class ExecutionDetailModel(BaseModel):
    execution_id: str
    user_id: str
    language: str
    status: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    termination_reason: str | None = None
    compilation_duration_ms: int | None = None
    error_message: str | None = None
    resource_usage: ResourceUsageModel = Field(default_factory=ResourceUsageModel)


class ExecutionSummaryItem(BaseModel):
    execution_id: str
    language: str
    status: str
    submitted_at: str
    exit_code: int | None = None
    termination_reason: str | None = None
    wall_time_ms: int = 0


class ExecutionListResponseModel(BaseModel):
    count: int
    executions: list[ExecutionSummaryItem]


class HealthResponseModel(BaseModel):
    status: str
    supervisor_binary: bool
    cgroup_v2: bool
    active_workers: int
    queue_depth: int


class MetricsResponseModel(BaseModel):
    executions: dict[str, Any]
    active_jobs: int
    queue_size: int
    max_concurrency: int
