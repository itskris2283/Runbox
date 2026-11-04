import time
from collections import defaultdict

from fastapi import HTTPException, status

from api.security.auth import AuthenticatedUser


class SlidingWindowRateLimiter:
    """
    In-memory sliding window rate limiter tracking request timestamps per user.
    """

    def __init__(self):
        # Format: {user_id: [timestamp, timestamp, ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(self, user: AuthenticatedUser, window_seconds: float = 60.0):
        if user.role == "admin":
            return  # Admins bypass normal rate limits

        now = time.time()
        cutoff = now - window_seconds
        timestamps = self._requests[user.user_id]

        # Evict timestamps older than the sliding window
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if valid_timestamps:
            self._requests[user.user_id] = valid_timestamps
        else:
            self._requests.pop(user.user_id, None)

        if len(valid_timestamps) >= user.rate_limit_per_min:
            retry_after = int(valid_timestamps[0] + window_seconds - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({user.rate_limit_per_min} req/min). Try again in {retry_after}s.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        self._requests[user.user_id].append(now)

    def reset(self):
        self._requests.clear()


rate_limiter = SlidingWindowRateLimiter()
