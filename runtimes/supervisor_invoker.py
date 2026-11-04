import asyncio
import contextlib
import json
import os
import signal
from typing import Any

from runtimes.base import ExecutionResponse, ResourceUsage


def resolve_supervisor_bin() -> str:
    env_bin = os.environ.get("RUNBOX_SUPERVISOR_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    release_bin = os.path.join(base_dir, "build-release", "runbox-supervisor")
    if os.path.exists(release_bin):
        return release_bin
    return os.path.join(base_dir, "build", "runbox-supervisor")


SUPERVISOR_PATH = resolve_supervisor_bin()

# Track active supervisor subprocesses for deterministic lifecycle termination
_active_processes: dict[str, asyncio.subprocess.Process] = {}


def kill_active_process(execution_id: str) -> None:
    """Immediately kills the supervisor process for a specific execution if still running."""
    proc = _active_processes.get(execution_id)
    if proc and proc.returncode is None:
        with contextlib.suppress(ProcessLookupError, Exception):
            proc.kill()
        if proc.pid:
            with contextlib.suppress(ProcessLookupError, Exception):
                os.kill(proc.pid, signal.SIGKILL)


def kill_all_active_processes() -> None:
    """Immediately kills all active supervisor subprocesses."""
    for proc in list(_active_processes.values()):
        if proc and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, Exception):
                proc.kill()
            if proc.pid:
                with contextlib.suppress(ProcessLookupError, Exception):
                    os.kill(proc.pid, signal.SIGKILL)


async def invoke_supervisor(
    execution_id: str,
    executable_path: str,
    argv: list[str],
    language: str,
    workspace_dir: str,
    stdin_data: str,
    limits: dict[str, Any],
) -> ExecutionResponse:
    config = {
        "execution_id": execution_id,
        "language": language,
        "executable_path": executable_path,
        "argv": argv,
        "workspace_dir": workspace_dir,
        "stdin": stdin_data,
        "limits": limits,
    }

    config_json = json.dumps(config)
    cmd = [SUPERVISOR_PATH, "--json", config_json]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _active_processes[execution_id] = proc
        stdout_bytes, stderr_bytes = await proc.communicate()
    except asyncio.CancelledError:
        if proc and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, Exception):
                proc.kill()
            if proc.pid:
                with contextlib.suppress(ProcessLookupError, Exception):
                    os.kill(proc.pid, signal.SIGKILL)
            with contextlib.suppress(Exception):
                await asyncio.shield(proc.wait())
        raise
    except Exception as e:
        return ExecutionResponse(
            execution_id=execution_id,
            status="failed",
            exit_code=1,
            stderr=f"Failed to launch supervisor: {e}",
            termination_reason="internal_error",
        )
    finally:
        _active_processes.pop(execution_id, None)

    out_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    if not out_str:
        return ExecutionResponse(
            execution_id=execution_id,
            status="failed",
            exit_code=proc.returncode if proc.returncode is not None else 1,
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            termination_reason="internal_error",
        )

    try:
        data = json.loads(out_str)
        ru = data.get("resource_usage", {})
        res_usage = ResourceUsage(
            wall_time_ms=ru.get("wall_time_ms", 0),
            cpu_time_ms=ru.get("cpu_time_ms", 0),
            memory_peak_bytes=ru.get("memory_peak_bytes", 0),
            pids_peak=ru.get("pids_peak", 0),
            oom_killed=ru.get("oom_killed", False),
        )

        term_reason = data.get("termination_reason", "normal_exit")
        status = data.get("status", "completed")
        if term_reason == "timed_out":
            status = "timed_out"
        elif term_reason in (
            "memory_limit_exceeded",
            "process_limit_exceeded",
            "output_limit_exceeded",
        ):
            status = "resource_limit_exceeded"

        return ExecutionResponse(
            execution_id=execution_id,
            status=status,
            exit_code=data.get("exit_code", 0),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            termination_reason=term_reason,
            resource_usage=res_usage,
        )
    except json.JSONDecodeError:
        return ExecutionResponse(
            execution_id=execution_id,
            status="failed",
            exit_code=1,
            stdout=out_str,
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            termination_reason="internal_error",
        )
