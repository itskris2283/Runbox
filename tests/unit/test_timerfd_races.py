import asyncio
import os
import shutil
import time

import pytest

from runtimes.supervisor_invoker import invoke_supervisor


@pytest.fixture
def workspace_tmp():
    ws = f"/tmp/runbox_test_timerfd_{int(time.time() * 1000)}"
    os.makedirs(ws, exist_ok=True)
    yield ws
    shutil.rmtree(ws, ignore_errors=True)


@pytest.mark.asyncio
async def test_timerfd_subsecond_deadline_precision(workspace_tmp):
    """Confirm kernel timerfd triggers monotonic timeout deadline with precision."""
    script_path = os.path.join(workspace_tmp, "main.py")
    with open(script_path, "w") as f:
        f.write("import time\ntime.sleep(5)\n")

    t0 = time.perf_counter()
    resp = await invoke_supervisor(
        execution_id="test-timerfd-prec",
        executable_path="/usr/bin/python3",
        argv=["-u", "main.py"],
        language="python",
        workspace_dir=workspace_tmp,
        stdin_data="",
        limits={"timeout_ms": 500, "memory_mb": 64},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status == "timed_out"
    assert resp.termination_reason == "timed_out"
    # Verify subsecond deadline was enforced near 500ms (within 100ms tolerance)
    assert 480 <= elapsed_ms <= 650
    assert resp.resource_usage.wall_time_ms >= 500


@pytest.mark.asyncio
async def test_fast_exit_before_timerfd_fires(workspace_tmp):
    """Confirm fast exiting process terminates immediately without waiting for timerfd."""
    script_path = os.path.join(workspace_tmp, "main.py")
    with open(script_path, "w") as f:
        f.write("print('FAST_EXIT_OK')\n")

    t0 = time.perf_counter()
    resp = await invoke_supervisor(
        execution_id="test-timerfd-fast",
        executable_path="/usr/bin/python3",
        argv=["-u", "main.py"],
        language="python",
        workspace_dir=workspace_tmp,
        stdin_data="",
        limits={"timeout_ms": 5000, "memory_mb": 64},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status == "completed"
    assert resp.exit_code == 0
    assert "FAST_EXIT_OK" in resp.stdout
    # Should complete well before 5000ms deadline
    assert elapsed_ms < 1500


@pytest.mark.asyncio
async def test_child_exit_racing_near_timeout(workspace_tmp):
    """Confirm process completing right around deadline handles race cleanly."""
    script_path = os.path.join(workspace_tmp, "main.py")
    with open(script_path, "w") as f:
        f.write("import time\ntime.sleep(0.35)\nprint('RACE_OK')\n")

    resp = await invoke_supervisor(
        execution_id="test-timerfd-race",
        executable_path="/usr/bin/python3",
        argv=["-u", "main.py"],
        language="python",
        workspace_dir=workspace_tmp,
        stdin_data="",
        limits={"timeout_ms": 400, "memory_mb": 64},
    )

    # Either completed successfully or timed out; must never hang or crash
    assert resp.status in ("completed", "timed_out")
    if resp.status == "completed":
        assert "RACE_OK" in resp.stdout


@pytest.mark.asyncio
async def test_cancellation_during_sleep(workspace_tmp):
    """Confirm supervisor subprocess cancellation terminates cleanly when task is cancelled."""
    script_path = os.path.join(workspace_tmp, "main.py")
    with open(script_path, "w") as f:
        f.write("import time\ntime.sleep(10)\n")

    task = asyncio.create_task(
        invoke_supervisor(
            execution_id="test-timerfd-cancel",
            executable_path="/usr/bin/python3",
            argv=["-u", "main.py"],
            language="python",
            workspace_dir=workspace_tmp,
            stdin_data="",
            limits={"timeout_ms": 5000, "memory_mb": 64},
        )
    )

    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
