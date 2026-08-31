"""
Dashboard aggregation queries (Milestone 16) — the owner's operational
view: active/delayed/completed counts, unbilled additional work, and the
Product Definition's headline metrics (avg completion time, revenue per
technician, average order value, repeat-customer rate, warranty case
count).

Every metric's exact definition is spelled out in its own function below,
deliberately verbosely — the roadmap's own risk assessment for this
milestone is "metrics that are subtly wrong (off-by-one in date ranges,
double-counting), not that the feature is hard to build," so ambiguity
here is the actual risk, not query syntax. Each one is verified in
test_dashboard.py against a hand-computed expected value on a seeded
dataset, not just "the query doesn't raise."

Uses SQLAlchemy's query builder with aggregate functions (func.count,
func.avg, func.sum) throughout rather than raw SQL — the Technical
Blueprint flags this milestone as "likely" (not certainly) needing raw
SQL/window functions for performance; at MVP data volumes the ORM-level
aggregates compile to the same simple GROUP BY/aggregate SQL a hand-
written query would, so there's nothing raw SQL would buy here.

Date-range filtering: `date_from`/`date_to` are plain dates (day
granularity, matching how an owner would actually pick a range in a UI).
Each is converted to a full-day datetime boundary — `date_from` becomes
00:00:00 UTC that day, `date_to` becomes 23:59:59.999999 UTC that day —
so both ends of the range are inclusive of the entire calendar day, never
silently excluding same-day activity (the exact "off-by-one in date
ranges" failure mode called out above).
"""

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.additional_work_item import AdditionalWorkItem, AdditionalWorkStatus
from app.models.job import Job, JobStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User

# Jobs not yet in a terminal state — the natural complement to "completed"
# and the superset "delayed" is drawn from. No single roadmap sentence
# defines "active" precisely, so this is the one metric definition that's
# an explicit design choice rather than a direct transcription: anything
# still in flight (new, assigned, en_route, in_progress, awaiting_parts,
# awaiting_approval) counts, cancelled does not (it's terminal, just not
# a success).
_NON_TERMINAL_STATUSES = [
    s for s in JobStatus if s not in (JobStatus.COMPLETED, JobStatus.CANCELLED)
]

# "Unbilled" for the summary's operational nudge means "still needs
# action" — pending (needs an approve/reject decision) or approved (needs
# invoicing). Rejected items are resolved and will never be billed, so
# they don't count as outstanding work; billed items are already done.
_UNBILLED_ADDITIONAL_WORK_STATUSES = [AdditionalWorkStatus.PENDING, AdditionalWorkStatus.APPROVED]


def _range_start(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min, tzinfo=timezone.utc) if d is not None else None


def _range_end(d: date | None) -> datetime | None:
    return datetime.combine(d, time.max, tzinfo=timezone.utc) if d is not None else None


async def get_summary(
    db: AsyncSession, organization_id: uuid.UUID, *, date_from: date | None, date_to: date | None
) -> dict:
    range_start = _range_start(date_from)
    range_end = _range_end(date_to)

    # Active and delayed are current-state snapshots, not period totals —
    # "how many jobs are active right now" doesn't have a meaningful
    # date-range reading, so these two deliberately ignore date_from/
    # date_to regardless of what's passed. Only "completed" and "unbilled
    # additional work" (each has a natural per-item timestamp to filter
    # on) respect the range.
    active_jobs = await _count(
        db,
        select(func.count()).select_from(Job).where(
            Job.organization_id == organization_id,
            Job.status.in_(_NON_TERMINAL_STATUSES),
        ),
    )

    now = datetime.now(timezone.utc)
    delayed_jobs = await _count(
        db,
        select(func.count()).select_from(Job).where(
            Job.organization_id == organization_id,
            Job.scheduled_at.is_not(None),
            Job.scheduled_at < now,
            Job.status.in_(_NON_TERMINAL_STATUSES),
        ),
    )

    completed_stmt = select(func.count()).select_from(Job).where(
        Job.organization_id == organization_id, Job.status == JobStatus.COMPLETED
    )
    if range_start is not None:
        completed_stmt = completed_stmt.where(Job.completed_at >= range_start)
    if range_end is not None:
        completed_stmt = completed_stmt.where(Job.completed_at <= range_end)
    completed_jobs = await _count(db, completed_stmt)

    unbilled_stmt = select(func.count()).select_from(AdditionalWorkItem).where(
        AdditionalWorkItem.organization_id == organization_id,
        AdditionalWorkItem.status.in_(_UNBILLED_ADDITIONAL_WORK_STATUSES),
    )
    if range_start is not None:
        unbilled_stmt = unbilled_stmt.where(AdditionalWorkItem.created_at >= range_start)
    if range_end is not None:
        unbilled_stmt = unbilled_stmt.where(AdditionalWorkItem.created_at <= range_end)
    unbilled_additional_work = await _count(db, unbilled_stmt)

    return {
        "active_jobs": active_jobs,
        "delayed_jobs": delayed_jobs,
        "completed_jobs": completed_jobs,
        "unbilled_additional_work": unbilled_additional_work,
    }


async def get_metrics(
    db: AsyncSession, organization_id: uuid.UUID, *, date_from: date | None, date_to: date | None
) -> dict:
    range_start = _range_start(date_from)
    range_end = _range_end(date_to)

    avg_completion_time_hours = await _avg_completion_time_hours(db, organization_id, range_start, range_end)
    revenue_per_technician = await _revenue_per_technician(db, organization_id, range_start, range_end)
    average_order_value = await _average_order_value(db, organization_id, range_start, range_end)
    repeat_customer_rate = await _repeat_customer_rate(db, organization_id, range_start, range_end)
    warranty_case_count = await _warranty_case_count(db, organization_id, range_start, range_end)

    return {
        "avg_completion_time_hours": avg_completion_time_hours,
        "revenue_per_technician": revenue_per_technician,
        "average_order_value": average_order_value,
        "repeat_customer_rate": repeat_customer_rate,
        "warranty_case_count": warranty_case_count,
    }


async def _avg_completion_time_hours(
    db: AsyncSession, organization_id: uuid.UUID, range_start: datetime | None, range_end: datetime | None
) -> float | None:
    """Average (completed_at - created_at) across completed jobs, in hours. Filtered by completed_at (when the job actually finished)."""
    stmt = select(func.avg(func.extract("epoch", Job.completed_at - Job.created_at))).where(
        Job.organization_id == organization_id, Job.status == JobStatus.COMPLETED
    )
    if range_start is not None:
        stmt = stmt.where(Job.completed_at >= range_start)
    if range_end is not None:
        stmt = stmt.where(Job.completed_at <= range_end)
    avg_seconds = (await db.execute(stmt)).scalar_one()
    return (avg_seconds / 3600) if avg_seconds is not None else None


async def _revenue_per_technician(
    db: AsyncSession, organization_id: uuid.UUID, range_start: datetime | None, range_end: datetime | None
) -> list[dict]:
    """
    Sum of paid payments per assigned technician. Filtered by
    payments.paid_at (when the money actually came in), not job dates —
    revenue belongs to the period it was collected in. The join to `users`
    is INNER, which naturally excludes jobs with no assigned technician
    (no separate IS NOT NULL filter needed).
    """
    stmt = (
        select(User.id, User.full_name, func.sum(Payment.amount))
        .select_from(Payment)
        .join(Job, Job.id == Payment.job_id)
        .join(User, User.id == Job.assigned_technician_id)
        .where(Job.organization_id == organization_id, Payment.status == PaymentStatus.PAID)
        .group_by(User.id, User.full_name)
        .order_by(User.full_name)
    )
    if range_start is not None:
        stmt = stmt.where(Payment.paid_at >= range_start)
    if range_end is not None:
        stmt = stmt.where(Payment.paid_at <= range_end)
    rows = (await db.execute(stmt)).all()
    return [{"technician_id": tech_id, "technician_name": name, "revenue": total} for tech_id, name, total in rows]


async def _average_order_value(
    db: AsyncSession, organization_id: uuid.UUID, range_start: datetime | None, range_end: datetime | None
):
    """Average paid-payment amount. Filtered by payments.paid_at, same reasoning as revenue_per_technician."""
    stmt = (
        select(func.avg(Payment.amount))
        .select_from(Payment)
        .join(Job, Job.id == Payment.job_id)
        .where(Job.organization_id == organization_id, Payment.status == PaymentStatus.PAID)
    )
    if range_start is not None:
        stmt = stmt.where(Payment.paid_at >= range_start)
    if range_end is not None:
        stmt = stmt.where(Payment.paid_at <= range_end)
    return (await db.execute(stmt)).scalar_one()


async def _repeat_customer_rate(
    db: AsyncSession, organization_id: uuid.UUID, range_start: datetime | None, range_end: datetime | None
) -> float:
    """
    (customers with >1 job in the period) / (customers with >=1 job in
    the period). Filtered by jobs.created_at — "within a period" applies
    to the whole metric, so a customer's job count here is their count of
    jobs *created in that window*, not their all-time count. Job status
    is deliberately ignored (a cancelled job still reflects a real
    customer contact). Returns 0.0 (not None) when there are no customers
    with jobs in the period — an empty period has a well-defined 0%
    repeat rate, not an undefined one.
    """
    stmt = select(Job.customer_id, func.count(Job.id)).where(Job.organization_id == organization_id)
    if range_start is not None:
        stmt = stmt.where(Job.created_at >= range_start)
    if range_end is not None:
        stmt = stmt.where(Job.created_at <= range_end)
    stmt = stmt.group_by(Job.customer_id)

    rows = (await db.execute(stmt)).all()
    total_customers = len(rows)
    if total_customers == 0:
        return 0.0
    repeat_customers = sum(1 for _, job_count in rows if job_count > 1)
    return repeat_customers / total_customers


async def _warranty_case_count(
    db: AsyncSession, organization_id: uuid.UUID, range_start: datetime | None, range_end: datetime | None
) -> int:
    """Count of jobs flagged as warranty claims. Filtered by jobs.created_at — when the claim was raised."""
    stmt = select(func.count()).select_from(Job).where(
        Job.organization_id == organization_id, Job.is_warranty_claim.is_(True)
    )
    if range_start is not None:
        stmt = stmt.where(Job.created_at >= range_start)
    if range_end is not None:
        stmt = stmt.where(Job.created_at <= range_end)
    return await _count(db, stmt)


async def _count(db: AsyncSession, stmt) -> int:
    return (await db.execute(stmt)).scalar_one()
