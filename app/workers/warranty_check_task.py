"""
Warranty-check scheduled task (Milestone 15) — the first scheduled
background task, per the Technical Blueprint's Section 9: "a daily-run
check via BackgroundTasks triggered on app startup with a simple
sleep-loop, or an external cron hitting an internal endpoint, is enough"
for the MVP.

Deliberately read-only and DB-write-free: the roadmap's own business logic
for this task says it "can simply update a computed flag or write a
log/timeline note... keep the actual 'notify someone' behavior out of
scope unless the Product Definition calls for it explicitly." Logging is
the simplest option that satisfies "for reporting purposes" without
inventing an "already flagged" tracking column Milestone 15 doesn't call
for ("Database changes: none new") — and because nothing is persisted,
running this any number of times is trivially safe, with no duplicate-
write risk to guard against.

Scans across ALL organizations, not one — unlike every other function in
this codebase, which takes an organization_id and scopes to one tenant,
this is a system-wide maintenance job with no "current organization"
context; it runs once per day for the whole deployment.

Production wiring (the actual startup loop or cron endpoint this
docstring describes) is deliberately not added in this milestone —
Milestone 15's own scope list is explicit that no new API endpoint is
introduced, and there's no automated-test-covered way to exercise a
real day-long sleep loop, so `run_warranty_check()` is implemented and
thoroughly tested as a standalone, directly-callable function; wiring it
to an actual scheduler is a deployment-time decision for whoever operates
this.

Milestone 17 added the try/except+log wrapper around the scan (see
`run_warranty_check`'s own docstring) — the one piece of hardening this
module was missing relative to `document_tasks.py`.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)

# How far ahead "approaching expiry" looks. Arbitrary but reasonable for
# an MVP reporting surface — nothing else reads this value, so it isn't
# exposed as a setting.
APPROACHING_EXPIRY_WINDOW_DAYS = 7


@dataclass
class WarrantyCheckResult:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    warranty_expires_at: date
    days_remaining: int


async def run_warranty_check() -> list[WarrantyCheckResult]:
    """
    Finds every completed job whose warranty expires today or within the
    next APPROACHING_EXPIRY_WINDOW_DAYS days (inclusive of both ends),
    logs each one, and returns what it found so callers/tests can inspect
    exactly what was flagged without parsing log output.

    Milestone 17 hardening: wrapped in the same try/except+log pattern as
    workers/document_tasks.py — this task has no request/response cycle
    to protect (it's meant to be driven by a scheduler, not a single
    HTTP request), but an unhandled exception here would still be a
    background task silently failing with no observable trace, which is
    exactly what this milestone's testing checklist rules out. On
    failure: log it, return an empty list rather than raise, so a
    transient DB hiccup on one run doesn't take down whatever process
    (a sleep-loop, a cron-triggered endpoint) is driving this.
    """
    try:
        async with AsyncSessionLocal() as db:
            results = await _scan(db)
    except Exception:
        logger.exception("Warranty check failed")
        return []

    for result in results:
        logger.info(
            "Warranty %s: job=%s organization=%s warranty_expires_at=%s days_remaining=%d",
            "expires today" if result.days_remaining == 0 else "approaching expiry",
            result.job_id,
            result.organization_id,
            result.warranty_expires_at,
            result.days_remaining,
        )
    logger.info(
        "Warranty check complete: %d job(s) with warranty expiring within %d day(s)",
        len(results),
        APPROACHING_EXPIRY_WINDOW_DAYS,
    )
    return results


async def _scan(db: AsyncSession) -> list[WarrantyCheckResult]:
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=APPROACHING_EXPIRY_WINDOW_DAYS)

    result = await db.execute(
        select(Job).where(
            Job.status == JobStatus.COMPLETED,
            Job.warranty_expires_at.is_not(None),
            Job.warranty_expires_at >= today,
            Job.warranty_expires_at <= horizon,
        )
    )
    jobs = result.scalars().all()

    return [
        WarrantyCheckResult(
            job_id=job.id,
            organization_id=job.organization_id,
            warranty_expires_at=job.warranty_expires_at,
            days_remaining=(job.warranty_expires_at - today).days,
        )
        for job in jobs
    ]
