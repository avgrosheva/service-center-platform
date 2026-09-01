"""
Minimal in-memory rate limiter for `/auth/login` (Milestone 19).

In-process and in-memory — no Redis, per the frozen MVP architecture
(Technical Blueprint Section 9's explicit "no Redis... until the arq
migration point" decision, which this doesn't change: a fixed-window
counter is a stateless in-memory dict, not a background job queue). This
means limits reset on process restart and aren't shared across multiple
worker processes — acceptable for the MVP's single-process deployment
(README's run instructions are `uvicorn app.main:app`, no multi-worker
setup); the natural trigger to move this to a shared store (Redis or
similar) is the same one that triggers the arq migration — real
production traffic across multiple processes.

Keyed by client IP alone, matching the roadmap's own scope for this
milestone ("Basic rate limiting on `/auth/*` endpoints (login
especially)") — not per-account, since combining both axes is exactly
the kind of defense-in-depth this MVP-stage checklist doesn't ask for.
Counts every attempt regardless of outcome (success or failure), which is
simpler than isolating failures only and matches how most real-world
login limiters behave; a legitimate user is only affected if they
themselves make several attempts in a short window, which is already an
edge case worth surfacing rather than silently allowing.

Only `/auth/login` is gated — register and refresh aren't credential-
guessing surfaces in the same way a password check is.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
_MAX_ATTEMPTS = 5

# client_ip -> list of attempt timestamps (time.monotonic()) within the
# current window. A plain module-level dict, not a class instance,
# mirrors app.database's module-level `engine` singleton — one shared
# store for the life of the process.
_attempts: dict[str, list[float]] = defaultdict(list)


def reset() -> None:
    """Test-only: clears all counters so tests don't leak state between each other (same role as conftest.py's `_dispose_engine_between_tests`)."""
    _attempts.clear()


async def enforce_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"

    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    recent_attempts = [t for t in _attempts[client_ip] if t > window_start]

    if len(recent_attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    recent_attempts.append(now)
    _attempts[client_ip] = recent_attempts
