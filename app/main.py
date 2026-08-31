"""
FastAPI application entrypoint.

Milestone 1 update: configuration now goes through app.config.Settings
instead of reading os.environ directly. Calling get_settings() at import
time (before the app object is even built) is what gives us "fail fast on
startup" — if DATABASE_URL or JWT_SECRET is missing, importing this module
raises a pydantic ValidationError immediately and the process refuses to
start, instead of failing on the first real request in production.

The real async SQLAlchemy engine/session wiring still lands in Milestone 2
(Database Infrastructure) — /health continues to use a direct asyncpg
connection as a minimal, temporary connectivity check.

Milestone 18 update: app construction moved into `create_app(settings)`
so the AI router can be registered conditionally on `settings.ai_enabled`
— and so tests can build two separate app instances (one with AI
enabled, one without) in the same process to prove routes genuinely
aren't registered when the flag is off, rather than merely blocked by a
role check. `app.routers.ai` itself is imported only inside the
`if settings.ai_enabled:` branch, not at module top level: with the flag
off, the AI router module — and anything it imports (the Anthropic
client construction in workers/ai_tasks.py) — is never even loaded,
which is the concrete mechanism behind "the app is fully functional with
every AI feature disabled."
"""

import asyncpg
from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.routers.auth import router as auth_router
from app.routers.customers import router as customers_router
from app.routers.dashboard import router as dashboard_router
from app.routers.equipment import router as equipment_router
from app.routers.job_items import router as job_items_router
from app.routers.jobs import router as jobs_router
from app.routers.payments import router as payments_router
from app.routers.users import router as users_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Field Service Platform",
        version="0.0.1",
        description="Backend API for the field service repair operations platform.",
    )
    register_exception_handlers(app)

    # Per the Technical Blueprint's API Design section: all business-domain
    # routes live under /api/v1, keeping /health outside it as an unversioned
    # ops endpoint.
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(customers_router, prefix="/api/v1")
    app.include_router(equipment_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(job_items_router, prefix="/api/v1")
    app.include_router(payments_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")

    if settings.ai_enabled:
        from app.routers.ai import router as ai_router

        app.include_router(ai_router, prefix="/api/v1")

    return app


# Fail fast: if required settings are missing, this raises now, at import
# time, so `uvicorn app.main:app` (or the docker container) refuses to
# start with a clear error — rather than starting "successfully" and only
# failing once a request needs a config value that was never set.
app = create_app()


@app.get("/health", tags=["system"])
async def health_check(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """
    Confirms the app is running and can reach the database.

    This is a minimal, direct asyncpg connectivity check — it intentionally
    does not go through the SQLAlchemy layer, since that layer doesn't exist
    yet at this milestone. Replace with a check through the real session
    factory once Milestone 2 is implemented.
    """
    try:
        # asyncpg expects a plain postgres:// DSN, not the SQLAlchemy-style
        # postgresql+asyncpg:// URL that later milestones will use for the
        # engine. Normalize here so the same setting works for both.
        asyncpg_dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn=asyncpg_dsn, timeout=3)
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 — broad on purpose for a health probe
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "detail": f"database unreachable: {exc}"},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "database": "connected", "environment": settings.environment},
    )
