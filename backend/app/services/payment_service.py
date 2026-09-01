"""
Payment management business logic (Milestone 13).

PUT is a genuine upsert per the roadmap ("creates if absent, updates if
present ... no separate create/update calls needed for a one-to-one
resource") — unlike every other job sub-resource so far, there's exactly
one payment per job, so "does a row already exist" is the only branch, not
a resource-id lookup.

Tenant-scoping reuses `job_service.get_scoped_job` directly, same as
`job_items_service.py`: a job_id belonging to another organization is
treated exactly like one that doesn't exist.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentUpsert
from app.services import job_service


class PaymentServiceError(Exception):
    """Base class for payment-service failures the router maps to HTTP status codes."""


class JobNotFoundError(PaymentServiceError):
    pass


class PaymentNotFoundError(PaymentServiceError):
    pass


async def get_payment(db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID) -> Payment:
    job = await job_service.get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")

    payment = await _get_payment_for_job(db, job.id)
    if payment is None:
        raise PaymentNotFoundError(f"No payment set for job {job_id}")
    return payment


async def upsert_payment(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, data: PaymentUpsert
) -> Payment:
    job = await job_service.get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")

    paid_at = data.paid_at
    if data.status == PaymentStatus.PAID and paid_at is None:
        paid_at = datetime.now(timezone.utc)

    payment = await _get_payment_for_job(db, job.id)
    if payment is None:
        payment = Payment(job_id=job.id, amount=data.amount, method=data.method, status=data.status, paid_at=paid_at)
        db.add(payment)
    else:
        payment.amount = data.amount
        payment.method = data.method
        payment.status = data.status
        payment.paid_at = paid_at

    await db.flush()
    await db.refresh(payment)
    return payment


async def _get_payment_for_job(db: AsyncSession, job_id: uuid.UUID) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.job_id == job_id))
    return result.scalar_one_or_none()
