import os

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.security.auth import (
    DEV_ADMIN_TOKEN,
    DEV_DEFAULT_TOKEN,
    TEST_TENANT_A_TOKEN,
    TEST_TENANT_B_TOKEN,
    AuthenticatedUser,
    get_current_user,
    hash_token,
    register_api_token,
    revoke_api_token,
)


def test_hash_token_sha256():
    h1 = hash_token("test_token_123")
    assert len(h1) == 64
    assert isinstance(h1, str)
    # Whitespace trimming check
    assert hash_token("  test_token_123  ") == h1
    assert hash_token("different_token") != h1


def test_get_current_user_with_x_api_key():
    user = get_current_user(x_api_key=DEV_DEFAULT_TOKEN, auth_cred=None)
    assert user.user_id == "usr_dev"
    assert user.role == "user"


def test_get_current_user_with_bearer_token():
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=DEV_ADMIN_TOKEN)
    user = get_current_user(x_api_key=None, auth_cred=cred)
    assert user.user_id == "usr_admin"
    assert user.role == "admin"


def test_get_current_user_tenant_a():
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=TEST_TENANT_A_TOKEN)
    user = get_current_user(x_api_key=None, auth_cred=cred)
    assert user.user_id == "usr_tenant_a"
    assert user.username == "tenant_a"


def test_get_current_user_tenant_b():
    user = get_current_user(x_api_key=TEST_TENANT_B_TOKEN, auth_cred=None)
    assert user.user_id == "usr_tenant_b"
    assert user.username == "tenant_b"


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(x_api_key="completely_bogus_token", auth_cred=None)
    assert exc_info.value.status_code == 401
    assert "Invalid API key" in exc_info.value.detail


def test_revoke_token_lifecycle():
    temp_token = "rbx_live_temp_test_token_abc"
    temp_user = AuthenticatedUser(
        user_id="usr_temp",
        username="temp_user",
        role="user",
        rate_limit_per_min=10,
        max_concurrency=2,
    )
    register_api_token(temp_token, temp_user)
    # Verify active
    user = get_current_user(x_api_key=temp_token, auth_cred=None)
    assert user.user_id == "usr_temp"

    # Revoke
    revoke_api_token(temp_token)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(x_api_key=temp_token, auth_cred=None)
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


def test_production_environment_fails_closed():
    old_env = os.environ.get("RUNBOX_ENV")
    try:
        os.environ["RUNBOX_ENV"] = "production"
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(x_api_key=None, auth_cred=None)
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail
    finally:
        if old_env is not None:
            os.environ["RUNBOX_ENV"] = old_env
        else:
            os.environ.pop("RUNBOX_ENV", None)


def test_development_environment_fallback():
    old_env = os.environ.get("RUNBOX_ENV")
    try:
        os.environ["RUNBOX_ENV"] = "development"
        user = get_current_user(x_api_key=None, auth_cred=None)
        assert user.user_id == "usr_dev"
        assert user.username == "dev_anonymous"
    finally:
        if old_env is not None:
            os.environ["RUNBOX_ENV"] = old_env
        else:
            os.environ.pop("RUNBOX_ENV", None)


def test_authenticated_user_model_defaults():
    user = AuthenticatedUser(user_id="usr_custom", username="custom")
    assert user.role == "user"
    assert user.rate_limit_per_min == 60
    assert user.max_concurrency == 5


def test_api_key_header_priority_over_bearer_when_both_present():
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=DEV_ADMIN_TOKEN)
    user = get_current_user(x_api_key=TEST_TENANT_A_TOKEN, auth_cred=cred)
    assert user.user_id == "usr_tenant_a"


def test_whitespace_padded_token_resolves():
    user = get_current_user(x_api_key=f"  {DEV_DEFAULT_TOKEN}  \n", auth_cred=None)
    assert user.user_id == "usr_dev"
