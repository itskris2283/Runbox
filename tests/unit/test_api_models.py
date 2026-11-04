import pytest
from pydantic import ValidationError

from runtimes.base import ExecutionLimits, ExecutionRequest


def test_execution_request_valid():
    req = ExecutionRequest(
        language="python",
        source_code="print('test')",
        limits=ExecutionLimits(timeout_ms=2000, memory_mb=64),
    )
    assert req.language == "python"
    assert req.source_code == "print('test')"
    assert req.limits.timeout_ms == 2000
    assert req.limits.memory_mb == 64


def test_execution_limits_clamping_constraints():
    # Lower bound validation
    with pytest.raises(ValidationError):
        ExecutionLimits(timeout_ms=50)  # ge=100

    with pytest.raises(ValidationError):
        ExecutionLimits(memory_mb=8)  # ge=16

    with pytest.raises(ValidationError):
        ExecutionLimits(process_limit=0)  # ge=1


def test_execution_limits_upper_bound():
    with pytest.raises(ValidationError):
        ExecutionLimits(timeout_ms=100000)  # le=60000
