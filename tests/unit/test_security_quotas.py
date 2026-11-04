import time

import pytest
from fastapi import HTTPException

from api.security.auth import AuthenticatedUser
from api.security.quotas import UserQuotaManager
from api.security.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_allows_within_limit():
    limiter = SlidingWindowRateLimiter()
    user = AuthenticatedUser(user_id="usr_test_1", username="test1", rate_limit_per_min=5)

    # Allow up to 5 requests
    for _ in range(5):
        limiter.check_rate_limit(user, window_seconds=60.0)


def test_rate_limiter_blocks_on_excess():
    limiter = SlidingWindowRateLimiter()
    user = AuthenticatedUser(user_id="usr_test_2", username="test2", rate_limit_per_min=3)

    for _ in range(3):
        limiter.check_rate_limit(user, window_seconds=60.0)

    # 4th request must be rejected with 429
    with pytest.raises(HTTPException) as exc_info:
        limiter.check_rate_limit(user, window_seconds=60.0)

    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert retry_after >= 1


def test_rate_limiter_admin_bypass():
    limiter = SlidingWindowRateLimiter()
    admin = AuthenticatedUser(
        user_id="usr_admin", username="admin", role="admin", rate_limit_per_min=1
    )

    # Admin should never be blocked even after exceeding limit
    for _ in range(10):
        limiter.check_rate_limit(admin, window_seconds=60.0)


def test_rate_limiter_sliding_window_expiration():
    limiter = SlidingWindowRateLimiter()
    user = AuthenticatedUser(user_id="usr_test_3", username="test3", rate_limit_per_min=2)

    # Inject timestamps from 70 seconds ago
    old_time = time.time() - 70.0
    limiter._requests[user.user_id] = [old_time, old_time]

    # Should evict the old timestamps and allow the request
    limiter.check_rate_limit(user, window_seconds=60.0)
    assert len(limiter._requests[user.user_id]) == 1


def test_rate_limiter_reset():
    limiter = SlidingWindowRateLimiter()
    user = AuthenticatedUser(user_id="usr_test_4", username="test4", rate_limit_per_min=1)
    limiter.check_rate_limit(user)
    limiter.reset()
    assert len(limiter._requests) == 0
    # Can make request again
    limiter.check_rate_limit(user)


def test_quota_manager_acquire_and_release():
    qm = UserQuotaManager()
    user = AuthenticatedUser(user_id="usr_q1", username="q1", max_concurrency=2)

    qm.acquire_slot(user)
    assert qm.get_active_count("usr_q1") == 1

    qm.acquire_slot(user)
    assert qm.get_active_count("usr_q1") == 2

    qm.release_slot("usr_q1")
    assert qm.get_active_count("usr_q1") == 1

    qm.release_slot("usr_q1")
    assert qm.get_active_count("usr_q1") == 0


def test_quota_manager_blocks_when_exhausted():
    qm = UserQuotaManager()
    user = AuthenticatedUser(user_id="usr_q2", username="q2", max_concurrency=2)

    qm.acquire_slot(user)
    qm.acquire_slot(user)

    with pytest.raises(HTTPException) as exc_info:
        qm.acquire_slot(user)

    assert exc_info.value.status_code == 429
    assert "Concurrent job limit exceeded" in exc_info.value.detail


def test_quota_manager_admin_bypass():
    qm = UserQuotaManager()
    admin = AuthenticatedUser(
        user_id="usr_admin", username="admin", role="admin", max_concurrency=1
    )

    # Admin should bypass concurrency checks without throwing
    for _ in range(5):
        qm.acquire_slot(admin)
    assert qm.get_active_count("usr_admin") == 0


def test_quota_manager_independent_user_limits():
    qm = UserQuotaManager()
    user_a = AuthenticatedUser(user_id="usr_a", username="user_a", max_concurrency=1)
    user_b = AuthenticatedUser(user_id="usr_b", username="user_b", max_concurrency=2)

    qm.acquire_slot(user_a)
    assert qm.get_active_count("usr_a") == 1

    # user_a is at limit
    with pytest.raises(HTTPException):
        qm.acquire_slot(user_a)

    # user_b should still acquire slot without interference
    qm.acquire_slot(user_b)
    assert qm.get_active_count("usr_b") == 1


def test_quota_manager_release_underflow_safety():
    qm = UserQuotaManager()
    # Releasing when 0 active jobs should not go negative
    qm.release_slot("usr_nonexistent")
    assert qm.get_active_count("usr_nonexistent") == 0


def test_quota_manager_reset():
    qm = UserQuotaManager()
    user = AuthenticatedUser(user_id="usr_q3", username="q3", max_concurrency=5)
    qm.acquire_slot(user)
    assert qm.get_active_count("usr_q3") == 1
    qm.reset()
    assert qm.get_active_count("usr_q3") == 0
