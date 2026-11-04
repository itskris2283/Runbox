from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ExecutionLimits(BaseModel):
    timeout_ms: int = Field(default=3000, ge=100, le=60000)
    memory_mb: int = Field(default=128, ge=16, le=2048)
    cpu_quota_percent: int = Field(default=50, ge=5, le=100)
    process_limit: int = Field(default=32, ge=1, le=128)
    output_limit_bytes: int = Field(default=1048576, ge=1024, le=10485760)


class ExecutionRequest(BaseModel):
    language: str
    source_code: str
    stdin: str = ""
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)


class ResourceUsage(BaseModel):
    wall_time_ms: int = 0
    cpu_time_ms: int = 0
    memory_peak_bytes: int = 0
    pids_peak: int = 0
    oom_killed: bool = False


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str  # "completed", "failed", "timed_out", "resource_limit_exceeded", "rejected"
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    termination_reason: str = "normal_exit"
    compilation_duration_ms: int | None = None
    resource_usage: ResourceUsage = Field(default_factory=ResourceUsage)


class BaseRuntime(ABC):
    @abstractmethod
    async def execute(
        self, execution_id: str, request: ExecutionRequest, workspace_dir: str
    ) -> ExecutionResponse:
        pass
