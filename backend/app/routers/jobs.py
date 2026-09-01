"""
Job endpoints.

Milestone 8 shipped creation, listing, detail, editable-field update, and
soft cancellation, gated all-or-nothing to owner/dispatcher — a deliberate,
documented-as-temporary broadening, since nothing could assign a
technician to a job yet.

Milestone 9 replaces that blanket gate with the real design: two role
dependencies instead of one.

- `_can_manage_jobs` (owner/dispatcher only) — create, editable-field
  update, assign, and cancel. These are dispatch/office actions; nothing
  here is part of a technician's role per the Technical Blueprint's role
  table.
- `_can_view_or_act_on_jobs` (owner/dispatcher/technician) — list, detail,
  status transitions, and the timeline. A technician passes this gate but
  then `job_service` enforces the actual restriction: owner/dispatcher see
  and act on every job in the organization; a technician is scoped to only
  the job(s) assigned to them (`list` transparently filters to their own,
  `detail`/`status`/`timeline` 403 — not 404, since the job genuinely
  exists in their own organization — on any job that isn't theirs).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.job import JobStatus
from app.models.user import User, UserRole
from app.schemas.job import JobAssignRequest, JobCreate, JobRead, JobStatusChangeRequest, JobUpdate
from app.schemas.job_status_history import JobStatusHistoryRead
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])

_can_manage_jobs = require_role(UserRole.OWNER, UserRole.DISPATCHER)
_can_view_or_act_on_jobs = require_role(UserRole.OWNER, UserRole.DISPATCHER, UserRole.TECHNICIAN)


@router.get("", response_model=list[JobRead])
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    assigned_technician_id: uuid.UUID | None = Query(default=None),
    scheduled_from: datetime | None = Query(default=None),
    scheduled_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_or_act_on_jobs),
) -> list:
    return await job_service.list_jobs(
        db,
        current_user.organization_id,
        requesting_user=current_user,
        status=status_filter,
        assigned_technician_id=assigned_technician_id,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
    )


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    data: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_jobs),
):
    try:
        return await job_service.create_job(db, current_user.organization_id, current_user.id, data)
    except job_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.EquipmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.EquipmentCustomerMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_or_act_on_jobs),
):
    try:
        return await job_service.get_job(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_jobs),
):
    try:
        return await job_service.update_job(db, current_user.organization_id, job_id, data)
    except job_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{job_id}", response_model=JobRead)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_jobs),
):
    try:
        return await job_service.cancel_job(db, current_user.organization_id, job_id, actor=current_user)
    except job_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{job_id}/assign", response_model=JobRead)
async def assign_technician(
    job_id: uuid.UUID,
    data: JobAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_jobs),
):
    try:
        return await job_service.assign_technician(
            db, current_user.organization_id, job_id, data.technician_id, actor=current_user
        )
    except (job_service.JobNotFoundError, job_service.TechnicianNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (job_service.InvalidTechnicianError, job_service.InvalidStatusTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{job_id}/status", response_model=JobRead)
async def change_status(
    job_id: uuid.UUID,
    data: JobStatusChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_or_act_on_jobs),
):
    try:
        return await job_service.change_status(
            db, current_user.organization_id, job_id, data.status, note=data.note, actor=current_user
        )
    except job_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except job_service.InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{job_id}/timeline", response_model=list[JobStatusHistoryRead])
async def get_timeline(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_view_or_act_on_jobs),
):
    try:
        return await job_service.get_timeline(
            db, current_user.organization_id, job_id, requesting_user=current_user
        )
    except job_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except job_service.ForbiddenJobAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
