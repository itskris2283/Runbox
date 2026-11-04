import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, db, scheduler


@pytest.fixture
async def client():
    await db.connect()
    if scheduler._running:
        await scheduler.stop()
    scheduler.queue = asyncio.Queue(maxsize=100)
    await scheduler.start()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await scheduler.stop()
    await db.close()


@pytest.mark.asyncio
async def test_health_endpoints(client):
    res = await client.get("/api/v1/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_ready = await client.get("/api/v1/health/ready")
    assert res_ready.status_code == 200
    assert "supervisor_binary" in res_ready.json()


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    res = await client.get("/api/v1/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "executions" in data
    assert "max_concurrency" in data


@pytest.mark.asyncio
async def test_post_execution_unsupported_language(client):
    payload = {"language": "brainfuck", "source_code": "+++++.", "limits": {"timeout_ms": 1000}}
    res = await client.post("/api/v1/executions", json=payload)
    assert res.status_code == 400
    assert "Unsupported language" in res.json()["detail"]


@pytest.mark.asyncio
async def test_post_python_execution_lifecycle(client):
    payload = {
        "language": "python",
        "source_code": "import math\nprint(f'PI={math.pi:.4f}')",
        "stdin": "",
        "limits": {
            "timeout_ms": 3000,
            "memory_mb": 128,
            "cpu_quota_percent": 50,
            "process_limit": 16,
            "output_limit_bytes": 1048576,
        },
    }
    res = await client.post("/api/v1/executions", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert "execution_id" in data
    exec_id = data["execution_id"]

    # Poll status until completed
    for _ in range(50):
        res_poll = await client.get(f"/api/v1/executions/{exec_id}")
        assert res_poll.status_code == 200
        p_data = res_poll.json()
        if p_data["status"] in ("completed", "failed", "timed_out"):
            break
        await asyncio.sleep(0.05)

    assert p_data["status"] == "completed"
    assert p_data["exit_code"] == 0
    assert "PI=3.1416" in p_data["stdout"]
    assert p_data["resource_usage"]["wall_time_ms"] > 0


@pytest.mark.asyncio
async def test_post_cpp_execution_lifecycle(client):
    cpp_source = """
    #include <iostream>
    int main() {
        std::cout << "CPP_RUNBOX_OK" << std::endl;
        return 0;
    }
    """
    payload = {
        "language": "cpp",
        "source_code": cpp_source,
        "limits": {"timeout_ms": 5000, "memory_mb": 128},
    }
    res = await client.post("/api/v1/executions", json=payload)
    assert res.status_code == 202
    exec_id = res.json()["execution_id"]

    for _ in range(100):
        res_poll = await client.get(f"/api/v1/executions/{exec_id}")
        p_data = res_poll.json()
        if p_data["status"] in ("completed", "failed", "timed_out"):
            break
        await asyncio.sleep(0.1)

    assert p_data["status"] == "completed"
    assert p_data["exit_code"] == 0
    assert "CPP_RUNBOX_OK" in p_data["stdout"]
    assert p_data["compilation_duration_ms"] is not None
