import contextlib

import pytest

from api.database.database import _active_databases, _open_databases
from api.main import db, scheduler
from api.scheduler.scheduler import _active_schedulers
from api.security.quotas import quota_manager
from api.security.rate_limiter import rate_limiter
from runtimes.supervisor_invoker import kill_all_active_processes


@pytest.fixture(autouse=True)
async def cleanup_test_resources():
    """Ensure all database connections and scheduler workers are cleanly closed after each test."""
    yield
    # 0. Terminate any lingering supervisor subprocesses
    kill_all_active_processes()

    # 1. Stop all active schedulers and cancel pending tasks
    schedulers_to_stop = set(list(_active_schedulers) + [scheduler])
    for s in schedulers_to_stop:
        with contextlib.suppress(Exception):
            if s._running:
                await s.stop()

    # 2. Close all active database connections to terminate background worker threads
    dbs_to_close = set(list(_open_databases) + list(_active_databases) + [db])
    for d in dbs_to_close:
        with contextlib.suppress(Exception):
            if d._conn is not None:
                await d.close()

    # 3. Reset rate limiter and quota counters
    rate_limiter.reset()
    quota_manager.reset()


def pytest_sessionfinish(session, exitstatus):
    """Fail-safe synchronous teardown on pytest session completion."""
    kill_all_active_processes()

    schedulers_to_stop = set(list(_active_schedulers) + [scheduler])
    for s in schedulers_to_stop:
        with contextlib.suppress(Exception):
            s.stop_sync()

    dbs_to_close = set(list(_open_databases) + list(_active_databases) + [db])
    for d in dbs_to_close:
        with contextlib.suppress(Exception):
            d.stop_sync()
