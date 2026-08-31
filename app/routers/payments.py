"""
Payment endpoints (Milestone 13).

Owner/dispatcher only, on both GET and PUT — technicians don't touch
financials at all per the Technical Blueprint's role table, and the
roadmap's own Milestone 13 testing checklist is explicit this is a full
block ("Technician blocked from this endpoint entirely"), not just a
write restriction the way additional-work's approve/reject/bill still
allowed technicians to view/flag.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.payment import PaymentRead, PaymentUpsert
from app.services import payment_service

router = APIRouter(prefix="/jobs/{job_id}/payment", tags=["payments"])

_can_manage_payment = require_role(UserRole.OWNER, UserRole.DISPATCHER)


@router.get("", response_model=PaymentRead)
async def get_payment(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_payment),
):
    try:
        return await payment_service.get_payment(db, current_user.organization_id, job_id)
    except payment_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except payment_service.PaymentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("", response_model=PaymentRead)
async def upsert_payment(
    job_id: uuid.UUID,
    data: PaymentUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_payment),
):
    try:
        return await payment_service.upsert_payment(db, current_user.organization_id, job_id, data)
    except payment_service.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
