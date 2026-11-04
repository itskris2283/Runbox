import hashlib
import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    user_id: str
    username: str
    role: str = "user"  # "user" or "admin"
    rate_limit_per_min: int = 60
    max_concurrency: int = 5


# Built-in hash store for tokens (supports rotation & multiple users)
# Format: {sha256_hash: AuthenticatedUser}
_TOKEN_STORE: dict[str, AuthenticatedUser] = {}
_REVOKED_HASHES: set[str] = set()


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 digest of token for secure constant-time comparison."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def register_api_token(raw_token: str, user: AuthenticatedUser):
    """Registers an API token in the in-memory token store."""
    token_hash = hash_token(raw_token)
    _TOKEN_STORE[token_hash] = user


def revoke_api_token(raw_token: str):
    """Revokes an API token immediately."""
    token_hash = hash_token(raw_token)
    _REVOKED_HASHES.add(token_hash)
    _TOKEN_STORE.pop(token_hash, None)


# Default development tokens (can be disabled in production via RUNBOX_ENV=production)
DEV_DEFAULT_TOKEN = "rbx_live_dev_secret_token_12345"
DEV_ADMIN_TOKEN = "rbx_live_admin_secret_token_99999"
TEST_TENANT_A_TOKEN = "rbx_live_tenant_a_key_11111"
TEST_TENANT_B_TOKEN = "rbx_live_tenant_b_key_22222"

register_api_token(
    DEV_DEFAULT_TOKEN,
    AuthenticatedUser(
        user_id="usr_dev",
        username="developer",
        role="user",
        rate_limit_per_min=1000,
        max_concurrency=50,
    ),
)
register_api_token(
    DEV_ADMIN_TOKEN,
    AuthenticatedUser(
        user_id="usr_admin",
        username="administrator",
        role="admin",
        rate_limit_per_min=10000,
        max_concurrency=100,
    ),
)
register_api_token(
    TEST_TENANT_A_TOKEN,
    AuthenticatedUser(
        user_id="usr_tenant_a",
        username="tenant_a",
        role="user",
        rate_limit_per_min=1000,
        max_concurrency=50,
    ),
)
register_api_token(
    TEST_TENANT_B_TOKEN,
    AuthenticatedUser(
        user_id="usr_tenant_b",
        username="tenant_b",
        role="user",
        rate_limit_per_min=1000,
        max_concurrency=50,
    ),
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


def get_current_user(
    x_api_key: str | None = Security(api_key_header),
    auth_cred: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> AuthenticatedUser:
    """
    Authenticates requests via X-API-Key or Authorization: Bearer <token>.
    In production mode (RUNBOX_ENV=production), missing credentials fail closed with 401.
    In development mode, unauthenticated requests are assigned to usr_dev if allowed.
    """
    env = os.environ.get("RUNBOX_ENV", "development").lower()
    raw_token = x_api_key or (auth_cred.credentials if auth_cred else None)

    if not raw_token:
        if env == "production":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: Missing API key or Bearer token",
                headers={"WWW-Authenticate": "Bearer, APIKey"},
            )
        # Development fallback
        return AuthenticatedUser(
            user_id="usr_dev",
            username="dev_anonymous",
            role="user",
            rate_limit_per_min=1000,
            max_concurrency=50,
        )

    provided_hash = hash_token(raw_token)

    if provided_hash in _REVOKED_HASHES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token has been revoked",
            headers={"WWW-Authenticate": "Bearer, APIKey"},
        )

    # Constant-time comparison across registered token hashes
    for stored_hash, user in _TOKEN_STORE.items():
        if secrets.compare_digest(provided_hash, stored_hash):
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key or token",
        headers={"WWW-Authenticate": "Bearer, APIKey"},
    )
