"""
Customer endpoints (Milestone 6).

Owner + dispatcher only, per the Technical Blueprint's role table
("Dispatcher: Create/edit jobs, customers, equipment...") — technicians
have no direct customer-record screen in the Product Definition's screen
list, so this module follows the same all-or-nothing role gate as
routers/users.py rather than users.py's split list/view-vs-write split.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])

_can_manage_customers = require_role(UserRole.OWNER, UserRole.DISPATCHER)


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    search: str | None = Query(default=None, description="Partial match against name or phone"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_customers),
) -> list:
    return await customer_service.list_customers(db, current_user.organization_id, search)


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_customers),
):
    return await customer_service.create_customer(db, current_user.organization_id, data)


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_customers),
):
    try:
        return await customer_service.get_customer(db, current_user.organization_id, customer_id)
    except customer_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_customers),
):
    try:
        return await customer_service.update_customer(db, current_user.organization_id, customer_id, data)
    except customer_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{customer_id}", response_model=CustomerRead)
async def archive_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_manage_customers),
):
    try:
        return await customer_service.archive_customer(db, current_user.organization_id, customer_id)
    except customer_service.CustomerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
