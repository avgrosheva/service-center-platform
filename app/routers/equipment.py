"""
Equipment endpoints (Milestone 7).

Owner + dispatcher only, same all-or-nothing role gate as
routers/customers.py, per the Technical Blueprint's role table
("Dispatcher: Create/edit jobs, customers, equipment...") — technicians
have no direct equipment-record screen in the Product Definition's screen
list.

Two route groups share this module because equipment is always reached
either through its owning customer (list/create) or directly by its own id
(detail/update) — matching the two API Design table entries in the
Technical Blueprint. Both are mounted under /api/v1 with no additional
router-level prefix, since neither shares a single common path segment.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.equipment import EquipmentCreate, EquipmentRead, EquipmentUpdate
from app.services import equipment_service

router = APIRouter(tags=["equipment"])

_can_manage_equipment = require_role(UserRole.OWNER, UserRole.DISPATCHER)


@router.get("/customers/{customer_id}/equipment", response_model=list[EquipmentRead])
async def list_equipment(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_equipment),
) -> list:
    try:
        return await equipment_service.list_equipment_for_customer(db, current_user.organization_id, customer_id)
    except equipment_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/customers/{customer_id}/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED
)
async def create_equipment(
    customer_id: uuid.UUID,
    data: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_equipment),
):
    try:
        return await equipment_service.create_equipment(db, current_user.organization_id, customer_id, data)
    except equipment_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
async def get_equipment(
    equipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_equipment),
):
    try:
        return await equipment_service.get_equipment(db, current_user.organization_id, equipment_id)
    except equipment_service.EquipmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: uuid.UUID,
    data: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_equipment),
):
    try:
        return await equipment_service.update_equipment(db, current_user.organization_id, equipment_id, data)
    except equipment_service.EquipmentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
