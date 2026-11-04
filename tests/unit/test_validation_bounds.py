import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.main import app
from api.models.execution import (
    MAX_SOURCE_CODE_BYTES,
    MAX_STDIN_BYTES,
    ExecutionLimitsModel,
    ExecutionRequestModel,
)


def test_source_code_max_boundary():
    # Exactly max bytes should pass
    exact_code = "x" * MAX_SOURCE_CODE_BYTES
    req = ExecutionRequestModel(language="python", source_code=exact_code)
    assert len(req.source_code) == MAX_SOURCE_CODE_BYTES

    # Exceeding by 1 byte should fail validation
    excess_code = "x" * (MAX_SOURCE_CODE_BYTES + 1)
    with pytest.raises(ValidationError) as exc:
        ExecutionRequestModel(language="python", source_code=excess_code)
    assert "source_code" in str(exc.value)


def test_stdin_max_boundary():
    exact_stdin = "y" * MAX_STDIN_BYTES
    req = ExecutionRequestModel(language="python", source_code="print(1)", stdin=exact_stdin)
    assert len(req.stdin) == MAX_STDIN_BYTES

    excess_stdin = "y" * (MAX_STDIN_BYTES + 1)
    with pytest.raises(ValidationError) as exc:
        ExecutionRequestModel(language="python", source_code="print(1)", stdin=excess_stdin)
    assert "stdin" in str(exc.value)


def test_limits_defaults():
    limits = ExecutionLimitsModel()
    assert limits.timeout_ms == 3000
    assert limits.memory_mb == 128
    assert limits.cpu_quota_percent == 50
    assert limits.process_limit == 32
    assert limits.output_limit_bytes == 1048576


def test_limits_lower_bounds_validation():
    # Test values below minimum threshold raise ValidationError
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(timeout_ms=5)  # min 10
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(memory_mb=10)  # min 16
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(cpu_quota_percent=0)  # min 1
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(process_limit=0)  # min 1
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(output_limit_bytes=500)  # min 1024


def test_limits_upper_bounds_validation():
    # Test values above maximum threshold raise ValidationError
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(timeout_ms=35000)  # max 30000
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(memory_mb=2048)  # max 1024
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(cpu_quota_percent=150)  # max 100
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(process_limit=128)  # max 64
    with pytest.raises(ValidationError):
        ExecutionLimitsModel(output_limit_bytes=10 * 1024 * 1024)  # max 5MB


def test_invalid_language_empty_string():
    with pytest.raises(ValidationError):
        ExecutionRequestModel(language="", source_code="print(1)")


def test_request_model_extra_fields_ignored_or_rejected():
    # Request model should parse without crashing
    req = ExecutionRequestModel(
        language="python", source_code="print(1)", limits=ExecutionLimitsModel(timeout_ms=2000)
    )
    assert req.limits.timeout_ms == 2000


@pytest.mark.asyncio
async def test_middleware_blocks_oversized_content_length():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Send a header claiming 2MB body
        headers = {"Content-Length": str(2 * 1024 * 1024), "Content-Type": "application/json"}
        res = await client.post("/api/v1/executions", headers=headers, content=b"{}")
        assert res.status_code == 413
        assert "exceeds maximum allowed size" in res.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_blocks_actual_oversized_body():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        oversized_body = b"x" * (1024 * 1024 + 1024)  # > 1MB
        res = await client.post(
            "/api/v1/executions",
            content=oversized_body,
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 413
