import os
import time

from runtimes.base import BaseRuntime, ExecutionRequest, ExecutionResponse
from runtimes.supervisor_invoker import invoke_supervisor


class CppRuntime(BaseRuntime):
    async def execute(
        self, execution_id: str, request: ExecutionRequest, workspace_dir: str
    ) -> ExecutionResponse:
        source_path = os.path.join(workspace_dir, "main.cpp")
        binary_path = os.path.join(workspace_dir, "main")

        with open(source_path, "w", encoding="utf-8") as f:
            f.write(request.source_code)

        # Stage 1: Isolated C++ Compilation
        compile_limits = {
            "timeout_ms": 10000,
            "memory_mb": 512,
            "cpu_quota_percent": 100,
            "process_limit": 32,
            "output_limit_bytes": 1048576,
        }

        t0 = time.monotonic()
        comp_res = await invoke_supervisor(
            execution_id=f"{execution_id}-comp",
            executable_path="/usr/bin/g++",
            argv=["-O0", "-std=c++20", "main.cpp", "-o", "main"],
            language="cpp_compile",
            workspace_dir=workspace_dir,
            stdin_data="",
            limits=compile_limits,
        )
        compile_duration_ms = int((time.monotonic() - t0) * 1000)

        if comp_res.exit_code != 0 or not os.path.exists(binary_path):
            comp_res.execution_id = execution_id
            comp_res.compilation_duration_ms = compile_duration_ms
            comp_res.status = "failed"
            comp_res.termination_reason = "compilation_error"
            return comp_res

        # Stage 2: Sandboxed Binary Execution
        run_limits = request.limits.model_dump()
        exec_res = await invoke_supervisor(
            execution_id=execution_id,
            executable_path="/workspace/main",
            argv=[],
            language="cpp",
            workspace_dir=workspace_dir,
            stdin_data=request.stdin,
            limits=run_limits,
        )
        exec_res.compilation_duration_ms = compile_duration_ms
        return exec_res
