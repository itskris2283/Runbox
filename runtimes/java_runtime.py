from runtimes.base import BaseRuntime, ExecutionRequest, ExecutionResponse


class JavaRuntime(BaseRuntime):
    async def execute(
        self, execution_id: str, request: ExecutionRequest, workspace_dir: str
    ) -> ExecutionResponse:
        return ExecutionResponse(
            execution_id=execution_id,
            status="rejected",
            exit_code=1,
            stderr="Java runtime milestone is scheduled for post-v0.1.0 hardening. JVM isolation profile not active.",
            termination_reason="runtime_not_enabled",
        )
