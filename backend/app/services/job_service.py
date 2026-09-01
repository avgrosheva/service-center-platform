"""
Job management business logic.

Milestone 8 gave this module creation, listing, editable-field updates, and
soft cancellation. Milestone 9 adds:

- A validated status-transition state machine (`_ALLOWED_TRANSITIONS`),
  replacing `cancel_job`'s previous unconditional overwrite with a real
  transition check — cancelling an already-completed/cancelled job is now
  correctly rejected instead of silently "succeeding."
- `assign_technician` and `change_status`, each writing an append-only
  `job_status_history` row.
- Full technician "own jobs only" scoping: `list_jobs`, `get_job`,
  `change_status`, and `get_timeline` all now take a `requesting_user` and
  enforce it via `check_technician_access` — a technician gets 403 (not a
  leaked 200, and not a tenant-isolation-style 404, since the job
  genuinely exists in their own organization) on any job that isn't
  assigned to them. `create_job`/`update_job`/`cancel_job`'s callers are
  still gated to owner/dispatcher at the router level, so those don't need
  the same check.

Tenant-scoping otherwise follows the Milestone 5-8 convention throughout:
organization_id always comes from current_user, every query filters by it,
and a customer_id/equipment_id/job_id/technician_id belonging to another
organization is treated exactly like one that doesn't exist.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.job import Job, JobStatus
from app.models.job_status_history import JobEventType, JobStatusHistory
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobUpdate

# Hardcoded per the roadmap's explicit Milestone 9 guidance ("hardcode a
# sensible default like 30/90 days for MVP, revisit configurability later")
# — this becomes an organization-level setting only once a real need for
# per-org variation shows up.
DEFAULT_WARRANTY_DAYS = 90

# The state machine, as a literal lookup table per the roadmap's explicit
# recommendation ("worth writing down as a literal lookup table in code...
# so they're easy to audit and extend") rather than scattered if-statements.
# `cancelled` is reachable from every non-terminal state; `completed` and
# `cancelled` are terminal (no outbound transitions).
_ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.NEW: {JobStatus.ASSIGNED, JobStatus.CANCELLED},
    JobStatus.ASSIGNED: {JobStatus.EN_ROUTE, JobStatus.CANCELLED},
    JobStatus.EN_ROUTE: {JobStatus.IN_PROGRESS, JobStatus.CANCELLED},
    JobStatus.IN_PROGRESS: {JobStatus.AWAITING_PARTS, JobStatus.AWAITING_APPROVAL, JobStatus.CANCELLED},
    JobStatus.AWAITING_PARTS: {JobStatus.IN_PROGRESS, JobStatus.CANCELLED},
    JobStatus.AWAITING_APPROVAL: {JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.CANCELLED: set(),
}


class JobServiceError(Exception):
    """Base class for job-service failures the router maps to HTTP status codes."""


class JobNotFoundError(JobServiceError):
    pass


class CustomerNotFoundError(JobServiceError):
    """Raised when a request's customer_id doesn't exist in the caller's organization."""


class EquipmentNotFoundError(JobServiceError):
    """Raised when a request's equipment_id doesn't exist in the caller's organization."""


class EquipmentCustomerMismatchError(JobServiceError):
    """Raised when equipment_id is provided but belongs to a different customer than customer_id."""


class ForbiddenJobAccessError(JobServiceError):
    """Raised when a technician acts on a job that isn't assigned to them."""


class InvalidStatusTransitionError(JobServiceError):
    """Raised when a requested status transition (or assignment) isn't allowed from the job's current status."""


class TechnicianNotFoundError(JobServiceError):
    """Raised when an assign request's technician_id doesn't exist in the caller's organization."""


class InvalidTechnicianError(JobServiceError):
    """Raised when an assign request's technician_id exists but isn't an active technician."""


def check_technician_access(job: Job, requesting_user: User) -> None:
    if requesting_user.role == UserRole.TECHNICIAN and job.assigned_technician_id != requesting_user.id:
        raise ForbiddenJobAccessError("You can only act on jobs assigned to you")


async def list_jobs(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    requesting_user: User,
    status: JobStatus | None = None,
    assigned_technician_id: uuid.UUID | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
) -> list[Job]:
    # A technician can never list anyone's jobs but their own — override
    # whatever the client asked for rather than merely AND-ing it in, so
    # there's no ambiguity about what a technician-supplied
    # assigned_technician_id query param does.
    if requesting_user.role == UserRole.TECHNICIAN:
        assigned_technician_id = requesting_user.id

    stmt = select(Job).where(Job.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if assigned_technician_id is not None:
        stmt = stmt.where(Job.assigned_technician_id == assigned_technician_id)
    if scheduled_from is not None:
        stmt = stmt.where(Job.scheduled_at >= scheduled_from)
    if scheduled_to is not None:
        stmt = stmt.where(Job.scheduled_at <= scheduled_to)
    stmt = stmt.order_by(Job.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_job(
    db: AsyncSession, organization_id: uuid.UUID, created_by_id: uuid.UUID, data: JobCreate
) -> Job:
    customer = await _get_scoped_customer(db, organization_id, data.customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"No customer {data.customer_id} in this organization")

    address_snapshot = data.address
    if data.equipment_id is not None:
        equipment = await _get_scoped_equipment(db, organization_id, data.equipment_id)
        if equipment is None:
            raise EquipmentNotFoundError(f"No equipment {data.equipment_id} in this organization")
        if equipment.customer_id != data.customer_id:
            raise EquipmentCustomerMismatchError(
                f"Equipment {data.equipment_id} does not belong to customer {data.customer_id}"
            )
        # The frozen address model's core guarantee: this is a one-time
        # copy of whatever installation_address reads *right now*. It is
        # never re-derived later, so a subsequent edit to
        # equipment.installation_address must never reach back and change
        # address_snapshot on this (or any other already-created) job.
        address_snapshot = equipment.installation_address

    is_warranty_claim, origin_job_id = await _resolve_warranty_claim(db, organization_id, data)

    job = Job(
        organization_id=organization_id,
        customer_id=data.customer_id,
        equipment_id=data.equipment_id,
        created_by_id=created_by_id,
        status=JobStatus.NEW,
        reported_issue=data.reported_issue,
        address_snapshot=address_snapshot,
        scheduled_at=data.scheduled_at,
        is_warranty_claim=is_warranty_claim,
        origin_job_id=origin_job_id,
    )
    db.add(job)
    await db.flush()
    return job


async def _resolve_warranty_claim(
    db: AsyncSession, organization_id: uuid.UUID, data: JobCreate
) -> tuple[bool, uuid.UUID | None]:
    """
    Milestone 15's auto-flagging rule: a new job on equipment with a
    still-valid warranty from a prior completed job is auto-flagged as a
    warranty claim and linked via origin_job_id. A client-supplied
    `is_warranty_claim` always wins over the auto-detected value ("a
    suggestion the dispatcher can override... never fully lock the
    field") — but origin_job_id is only ever set to a real match, never
    fabricated just because a caller forced `is_warranty_claim=True` with
    nothing to actually link to.
    """
    auto_origin_job = None
    if data.equipment_id is not None:
        auto_origin_job = await _find_active_warranty_origin(db, organization_id, data.equipment_id)

    if data.is_warranty_claim is not None:
        is_warranty_claim = data.is_warranty_claim
    else:
        is_warranty_claim = auto_origin_job is not None

    origin_job_id = auto_origin_job.id if (is_warranty_claim and auto_origin_job is not None) else None
    return is_warranty_claim, origin_job_id


async def _find_active_warranty_origin(
    db: AsyncSession, organization_id: uuid.UUID, equipment_id: uuid.UUID
) -> Job | None:
    """
    The most recent completed job on this equipment whose warranty hasn't
    expired yet (warranty_expires_at >= today, inclusive — a claim made on
    the exact expiry date still counts). With the current single hardcoded
    DEFAULT_WARRANTY_DAYS, "most recent completed" and "latest
    warranty_expires_at" are equivalent, but ordering by
    warranty_expires_at directly is what stays correct if per-org warranty
    periods are ever introduced later.
    """
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(Job)
        .where(
            Job.organization_id == organization_id,
            Job.equipment_id == equipment_id,
            Job.status == JobStatus.COMPLETED,
            Job.warranty_expires_at.is_not(None),
            Job.warranty_expires_at >= today,
        )
        .order_by(Job.warranty_expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_job(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> Job:
    job = await get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")
    check_technician_access(job, requesting_user)
    return job


async def update_job(db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, data: JobUpdate) -> Job:
    # Owner/dispatcher only (gated at the router) — editing intake fields
    # (issue/address/schedule) isn't part of a technician's role per the
    # Technical Blueprint's role table, so no technician-access check here.
    job = await get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")

    if data.reported_issue is not None:
        job.reported_issue = data.reported_issue
    if data.address_snapshot is not None:
        job.address_snapshot = data.address_snapshot
    if data.scheduled_at is not None:
        job.scheduled_at = data.scheduled_at

    await db.flush()
    # updated_at (server-side onupdate=func.now()) comes back expired after
    # an UPDATE under the async driver — see the same comment in
    # user_service.py / customer_service.py / equipment_service.py.
    await db.refresh(job)
    return job


async def assign_technician(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    technician_id: uuid.UUID,
    *,
    actor: User,
) -> Job:
    job = await get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")

    technician = await _get_scoped_user(db, organization_id, technician_id)
    if technician is None:
        raise TechnicianNotFoundError(f"No user {technician_id} in this organization")
    if technician.role != UserRole.TECHNICIAN or not technician.is_active:
        raise InvalidTechnicianError(f"User {technician_id} is not an active technician in this organization")

    # Milestone 9 scope: assignment is only meaningful from `new` (moving
    # the job to `assigned`), matching the roadmap's linear transition
    # chain literally. Reassigning an already-assigned/in-progress job to a
    # different technician isn't part of this milestone's tested scope —
    # revisit if a real reassignment need shows up.
    if job.status != JobStatus.NEW:
        raise InvalidStatusTransitionError(
            f"Cannot assign a technician to a job in status '{job.status.value}' (must be 'new')"
        )

    job.assigned_technician_id = technician.id
    job.status = JobStatus.ASSIGNED

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=actor.id,
            event_type=JobEventType.ASSIGNED.value,
            from_status=JobStatus.NEW,
            to_status=JobStatus.ASSIGNED,
            note=f"Assigned to {technician.full_name}",
        )
    )

    await db.flush()
    await db.refresh(job)
    return job


async def change_status(
    db: AsyncSession,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    new_status: JobStatus,
    *,
    note: str | None,
    actor: User,
) -> Job:
    job = await get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")
    check_technician_access(job, actor)

    allowed = _ALLOWED_TRANSITIONS.get(job.status, set())
    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Cannot transition job from '{job.status.value}' to '{new_status.value}'"
        )

    from_status = job.status
    job.status = new_status
    if new_status == JobStatus.COMPLETED:
        now = datetime.now(timezone.utc)
        job.completed_at = now
        job.warranty_expires_at = now.date() + timedelta(days=DEFAULT_WARRANTY_DAYS)

    db.add(
        JobStatusHistory(
            job_id=job.id,
            actor_id=actor.id,
            event_type=JobEventType.STATUS_CHANGED.value,
            from_status=from_status,
            to_status=new_status,
            note=note,
        )
    )

    await db.flush()
    await db.refresh(job)
    return job


async def cancel_job(db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, actor: User) -> Job:
    # Soft cancel, routed through the same validated state machine as
    # /jobs/{id}/status — this is what makes "cancelled reachable from any
    # non-terminal state" (and NOT reachable from a terminal one) actually
    # true, rather than the unconditional overwrite Milestone 8 shipped
    # before this state machine existed.
    return await change_status(db, organization_id, job_id, JobStatus.CANCELLED, note=None, actor=actor)


async def get_timeline(
    db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID, *, requesting_user: User
) -> list[JobStatusHistory]:
    job = await get_scoped_job(db, organization_id, job_id)
    if job is None:
        raise JobNotFoundError(f"No job {job_id} in this organization")
    check_technician_access(job, requesting_user)

    result = await db.execute(
        select(JobStatusHistory)
        .where(JobStatusHistory.job_id == job.id)
        .order_by(JobStatusHistory.created_at)
    )
    return list(result.scalars().all())


async def get_scoped_job(db: AsyncSession, organization_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    result = await db.execute(select(Job).where(Job.id == job_id, Job.organization_id == organization_id))
    return result.scalar_one_or_none()


async def _get_scoped_customer(
    db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer | None:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def _get_scoped_equipment(
    db: AsyncSession, organization_id: uuid.UUID, equipment_id: uuid.UUID
) -> Equipment | None:
    result = await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, Equipment.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def _get_scoped_user(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    return result.scalar_one_or_none()
