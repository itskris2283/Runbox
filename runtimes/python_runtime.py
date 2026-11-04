import os

from runtimes.base import BaseRuntime, ExecutionRequest, ExecutionResponse
from runtimes.supervisor_invoker import invoke_supervisor


class PythonRuntime(BaseRuntime):
    async def execute(
        self, execution_id: str, request: ExecutionRequest, workspace_dir: str
    ) -> ExecutionResponse:
        script_path = os.path.join(workspace_dir, "main.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(request.source_code)

        limits_dict = request.limits.model_dump()

        return await invoke_supervisor(
            execution_id=execution_id,
            executable_path="/usr/bin/python3",
            argv=["-B", "-u", "main.py"],
            language="python",
            workspace_dir=workspace_dir,
            stdin_data=request.stdin,
            limits=limits_dict,
        )
