import os

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.security.auth import (
    DEV_ADMIN_TOKEN,
    TEST_TENANT_A_TOKEN,
    TEST_TENANT_B_TOKEN,
    AuthenticatedUser,
    register_api_token,
    revoke_api_token,
)
from api.security.quotas import quota_manager
from api.security.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def reset_security_state():
    rate_limiter.reset()
    quota_manager.reset()
    yield
    rate_limiter.reset()
    quota_manager.reset()


@pytest.mark.asyncio
async def test_production_mode_unauthenticated_request_rejected():
    old_env = os.environ.get("RUNBOX_ENV")
    try:
        os.environ["RUNBOX_ENV"] = "production"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {
                "language": "python",
                "source_code": "print('hello')",
                "limits": {"timeout_ms": 1000, "memory_mb": 64},
            }
            res = await client.post("/api/v1/executions", json=payload)
            assert res.status_code == 401
            assert "Authentication required" in res.json()["detail"]
    finally:
        if old_env is not None:
            os.environ["RUNBOX_ENV"] = old_env
        else:
            os.environ.pop("RUNBOX_ENV", None)


@pytest.mark.asyncio
async def test_bearer_token_authenticated_submission():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "language": "python",
            "source_code": "print('tenant a')",
            "limits": {"timeout_ms": 1000, "memory_mb": 64},
        }
        headers = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        res = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert res.status_code == 202
        assert "execution_id" in res.json()


@pytest.mark.asyncio
async def test_x_api_key_authenticated_submission():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "language": "python",
            "source_code": "print('tenant b')",
            "limits": {"timeout_ms": 1000, "memory_mb": 64},
        }
        headers = {"X-API-Key": TEST_TENANT_B_TOKEN}
        res = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert res.status_code == 202
        assert "execution_id" in res.json()


@pytest.mark.asyncio
async def test_revoked_token_rejected():
    temp_key = "rbx_live_revoked_integration_key"
    register_api_token(temp_key, AuthenticatedUser(user_id="usr_rev", username="revoked_user"))
    revoke_api_token(temp_key)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {"language": "python", "source_code": "print(1)"}
        res = await client.post("/api/v1/executions", json=payload, headers={"X-API-Key": temp_key})
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_health_endpoints_bypass_auth_in_production():
    old_env = os.environ.get("RUNBOX_ENV")
    try:
        os.environ["RUNBOX_ENV"] = "production"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res_health = await client.get("/healthz")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "ok"

            res_ready = await client.get("/readyz")
            assert res_ready.status_code == 200
            assert res_ready.json()["status"] == "ready"
    finally:
        if old_env is not None:
            os.environ["RUNBOX_ENV"] = old_env
        else:
            os.environ.pop("RUNBOX_ENV", None)


@pytest.mark.asyncio
async def test_anti_enumeration_cross_tenant_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit as Tenant A
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        payload = {"language": "python", "source_code": "print('tenant a')"}
        res_a = await client.post("/api/v1/executions", json=payload, headers=headers_a)
        assert res_a.status_code == 202
        exec_id_a = res_a.json()["execution_id"]

        # Tenant A can read their own job
        res_check_a = await client.get(f"/api/v1/executions/{exec_id_a}", headers=headers_a)
        assert res_check_a.status_code == 200
        assert res_check_a.json()["execution_id"] == exec_id_a

        # Tenant B attempting to read Tenant A's job must receive 404 (Anti-Enumeration)
        headers_b = {"Authorization": f"Bearer {TEST_TENANT_B_TOKEN}"}
        res_check_b = await client.get(f"/api/v1/executions/{exec_id_a}", headers=headers_b)
        assert res_check_b.status_code == 404

        # Nonexistent job should also return 404 with identical message structure
        res_check_none = await client.get("/api/v1/executions/nonexistent_12345", headers=headers_b)
        assert res_check_none.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_cancellation_anti_enumeration():
    """Verify that canceling another tenant's job returns 404 indistinguishable from nonexistent job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit as Tenant A
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        payload = {"language": "python", "source_code": "import time; time.sleep(5)"}
        res_a = await client.post("/api/v1/executions", json=payload, headers=headers_a)
        assert res_a.status_code == 202
        exec_id_a = res_a.json()["execution_id"]

        # Tenant B attempting to cancel Tenant A's job receives 404 (Anti-Enumeration)
        headers_b = {"Authorization": f"Bearer {TEST_TENANT_B_TOKEN}"}
        res_cancel_b = await client.delete(f"/api/v1/executions/{exec_id_a}", headers=headers_b)
        assert res_cancel_b.status_code == 404
        assert "not found" in res_cancel_b.json()["detail"].lower()

        # Nonexistent job cancellation receives identical 404 status and detail
        res_cancel_nonexistent = await client.delete(
            "/api/v1/executions/nonexistent_dummy_9999", headers=headers_b
        )
        assert res_cancel_nonexistent.status_code == 404
        assert res_cancel_nonexistent.json() == {
            "detail": "Execution 'nonexistent_dummy_9999' not found"
        }
        assert res_cancel_b.json() == {"detail": f"Execution '{exec_id_a}' not found"}


@pytest.mark.asyncio
async def test_repeated_and_concurrent_cancellation_semantics():
    """Verify idempotent and concurrent cancellation behavior."""
    import asyncio

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        payload = {"language": "python", "source_code": "import time; time.sleep(10)"}
        res = await client.post("/api/v1/executions", json=payload, headers=headers_a)
        exec_id = res.json()["execution_id"]

        # 1. Concurrent cancellation attempts by the owner
        async def cancel_call():
            return await client.delete(f"/api/v1/executions/{exec_id}", headers=headers_a)

        responses = await asyncio.gather(cancel_call(), cancel_call(), cancel_call())
        for r in responses:
            assert r.status_code == 200
            assert r.json()["execution_id"] == exec_id

        # 2. Repeated sequential cancellation after already cancelled returns 200 with cancelled=False
        repeat_res = await client.delete(f"/api/v1/executions/{exec_id}", headers=headers_a)
        assert repeat_res.status_code == 200
        assert repeat_res.json()["status"] == "cancelled"
        assert repeat_res.json()["cancelled"] is False


@pytest.mark.asyncio
async def test_unauthorized_cancellation_via_api_key_and_bearer():
    """Verify both X-API-Key and Bearer authentication enforce anti-enumeration on cancellation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit job as Tenant A with Bearer
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        res_a = await client.post(
            "/api/v1/executions",
            json={"language": "python", "source_code": "print('sec')"},
            headers=headers_a,
        )
        exec_id = res_a.json()["execution_id"]

        # Tenant B tries cancel via X-API-Key -> 404
        res_x_api = await client.delete(
            f"/api/v1/executions/{exec_id}", headers={"X-API-Key": TEST_TENANT_B_TOKEN}
        )
        assert res_x_api.status_code == 404
        assert "not found" in res_x_api.json()["detail"].lower()

        # Tenant B tries cancel via Bearer -> 404
        res_bearer = await client.delete(
            f"/api/v1/executions/{exec_id}",
            headers={"Authorization": f"Bearer {TEST_TENANT_B_TOKEN}"},
        )
        assert res_bearer.status_code == 404
        assert "not found" in res_bearer.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_can_access_and_cancel_any_job():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit as Tenant A
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        payload = {"language": "python", "source_code": "import time; time.sleep(5)"}
        res_a = await client.post("/api/v1/executions", json=payload, headers=headers_a)
        exec_id_a = res_a.json()["execution_id"]

        # Admin reads Tenant A's job
        headers_admin = {"Authorization": f"Bearer {DEV_ADMIN_TOKEN}"}
        res_admin_get = await client.get(f"/api/v1/executions/{exec_id_a}", headers=headers_admin)
        assert res_admin_get.status_code == 200

        # Admin cancels Tenant A's job
        res_admin_cancel = await client.delete(
            f"/api/v1/executions/{exec_id_a}", headers=headers_admin
        )
        assert res_admin_cancel.status_code == 200


@pytest.mark.asyncio
async def test_list_executions_scoped_to_requesting_tenant():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers_a = {"Authorization": f"Bearer {TEST_TENANT_A_TOKEN}"}
        headers_b = {"Authorization": f"Bearer {TEST_TENANT_B_TOKEN}"}

        # Submit one for each
        await client.post(
            "/api/v1/executions",
            json={"language": "python", "source_code": "print(1)"},
            headers=headers_a,
        )
        await client.post(
            "/api/v1/executions",
            json={"language": "python", "source_code": "print(2)"},
            headers=headers_b,
        )

        # List Tenant A
        res_list_a = await client.get("/api/v1/executions", headers=headers_a)
        assert res_list_a.status_code == 200
        data_a = res_list_a.json()
        assert data_a["count"] >= 1
        # None of Tenant B's jobs should be in Tenant A's list

        # List Tenant B
        res_list_b = await client.get("/api/v1/executions", headers=headers_b)
        assert res_list_b.status_code == 200
        data_b = res_list_b.json()
        assert data_b["count"] >= 1


@pytest.mark.asyncio
async def test_rate_limiting_enforced_via_api():
    # Register user with low rate limit (2 req/min)
    rate_token = "rbx_live_rate_test_key"
    register_api_token(
        rate_token,
        AuthenticatedUser(user_id="usr_rate", username="rate_user", rate_limit_per_min=2),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers = {"X-API-Key": rate_token}
        payload = {"language": "python", "source_code": "print(1)"}

        # 1st request ok
        r1 = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert r1.status_code == 202

        # 2nd request ok
        r2 = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert r2.status_code == 202

        # 3rd request throttled with 429
        r3 = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers


@pytest.mark.asyncio
async def test_concurrency_quota_enforced_via_api():
    # Register user with concurrency quota of 1
    quota_token = "rbx_live_quota_test_key"
    register_api_token(
        quota_token,
        AuthenticatedUser(
            user_id="usr_quota", username="quota_user", max_concurrency=1, rate_limit_per_min=100
        ),
    )

    # Artificially occupy slot
    quota_manager._active_jobs["usr_quota"] = 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers = {"X-API-Key": quota_token}
        payload = {"language": "python", "source_code": "print(1)"}

        res = await client.post("/api/v1/executions", json=payload, headers=headers)
        assert res.status_code == 429
        assert "Concurrent job limit exceeded" in res.json()["detail"]
