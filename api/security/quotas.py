from collections import defaultdict

from fastapi import HTTPException, status

from api.security.auth import AuthenticatedUser


class UserQuotaManager:
    """
    Tracks and enforces maximum active concurrent execution jobs per user.
    Enforces exactly-once slot release per execution_id to prevent double releases
    or slot leaks during cancellation, timeouts, failures, or scheduler shutdown.
    """

    def __init__(self):
        self._active_jobs: dict[str, int] = defaultdict(int)
        self._execution_slots: dict[str, str] = {}  # execution_id -> user_id

    def acquire_slot(self, user: AuthenticatedUser, execution_id: str | None = None) -> None:
        if user.role == "admin":
            if execution_id:
                self._execution_slots[execution_id] = user.user_id
            return
        current_count = self._active_jobs[user.user_id]
        if current_count >= user.max_concurrency:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Concurrent job limit exceeded ({current_count}/{user.max_concurrency}). Wait for active jobs to complete.",
            )
        self._active_jobs[user.user_id] += 1
        if execution_id:
            self._execution_slots[execution_id] = user.user_id

    def register_execution(self, execution_id: str, user_id: str) -> None:
        """Associates an execution_id with an already acquired quota slot."""
        self._execution_slots[execution_id] = user_id

    def release_execution_slot(self, execution_id: str) -> bool:
        """
        Idempotently releases the quota slot held by execution_id.
        Returns True if the slot was released, False if already released or unmapped.
        """
        user_id = self._execution_slots.pop(execution_id, None)
        if user_id:
            if user_id != "usr_admin" and self._active_jobs[user_id] > 0:
                self._active_jobs[user_id] -= 1
                if self._active_jobs[user_id] == 0:
                    self._active_jobs.pop(user_id, None)
            return True
        return False

    def release_slot(self, user_id: str, execution_id: str | None = None) -> bool:
        """
        Releases a concurrency quota slot.
        If execution_id is provided, guarantees exactly-once release semantics.
        """
        if execution_id:
            return self.release_execution_slot(execution_id)

        # Fallback for callers releasing by user_id without execution_id
        if user_id != "usr_admin" and self._active_jobs[user_id] > 0:
            self._active_jobs[user_id] -= 1
            if self._active_jobs[user_id] == 0:
                self._active_jobs.pop(user_id, None)
            return True
        return False

    def get_active_count(self, user_id: str) -> int:
        return self._active_jobs.get(user_id, 0)

    def reset(self):
        self._active_jobs.clear()
        self._execution_slots.clear()


quota_manager = UserQuotaManager()
