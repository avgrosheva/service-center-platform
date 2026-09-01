"""
Session-wide test setup.

app.main calls get_settings() at import time (Milestone 1's fail-fast
behavior), so a valid DATABASE_URL and JWT_SECRET must exist before any
test module imports app.main.

If a real .env file exists in the project root (as it does for local
development), we leave it alone and let pydantic-settings read it
normally — setting env vars here would take priority over .env and
silently shadow real local values (e.g. a non-default Postgres port).
The hardcoded fallback below only kicks in when there's no .env at all
(e.g. a bare CI runner).
"""

import os
from pathlib import Path

import pytest

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

if not _ENV_FILE.exists():
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://fsp:dev_password_change_me@localhost:5432/field_service",
    )
    os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """
    pytest-asyncio gives each test function its own event loop (see
    asyncio_default_fixture_loop_scope = function in pytest.ini). The
    module-level `engine` in app.database is a singleton whose connection
    pool holds asyncpg connections bound to whichever loop created them.
    Without disposing the pool between tests, a test running on a new loop
    tries to reuse a connection tied to a previous (already-closed) loop
    and fails with "cannot perform operation: another operation is in
    progress" or InterfaceError — not a real bug in app.database, just a
    consequence of a process-wide singleton meeting per-test event loops.

    This is autouse and lives in the top-level conftest so every test file
    that touches the database gets this for free, instead of each test
    module needing its own copy of this fixture.
    """
    yield
    from app.database import engine

    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter():
    """
    app.core.rate_limit's counter (Milestone 19) is a module-level dict,
    same singleton-state shape as app.database's `engine` above — and
    every test in this suite that logs in shares the same fake client IP
    under httpx's ASGITransport, so without resetting between tests the
    whole suite's cumulative /auth/login calls (dozens, across many test
    files) would trip the 5-attempts-per-60s limit partway through a run
    and start failing unrelated tests with 429s that have nothing to do
    with what those tests are actually checking.
    """
    from app.core import rate_limit

    rate_limit.reset()
    yield
    rate_limit.reset()