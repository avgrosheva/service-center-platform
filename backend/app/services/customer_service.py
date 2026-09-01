"""
Customer management business logic (Milestone 6).

Follows the tenant-scoping convention established in Milestone 5:
organization_id always comes from current_user (never client input), every
query filters by it, and a customer_id belonging to another organization is
treated exactly like one that doesn't exist (CustomerNotFoundError -> 404).
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerServiceError(Exception):
    """Base class for customer-service failures the router maps to HTTP status codes."""


class CustomerNotFoundError(CustomerServiceError):
    pass


async def list_customers(
    db: AsyncSession, organization_id: uuid.UUID, search: str | None = None
) -> list[Customer]:
    # Archived customers are excluded from the default list (it should read
    # as "current customers"), but stay individually reachable via
    # get_customer — future equipment/job records will still need to
    # resolve an archived customer's details.
    stmt = select(Customer).where(Customer.organization_id == organization_id, Customer.is_active.is_(True))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(Customer.full_name.ilike(pattern), Customer.phone.ilike(pattern)))
    stmt = stmt.order_by(Customer.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_customer(db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = await _get_scoped_customer(db, organization_id, customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"No customer {customer_id} in this organization")
    return customer


async def create_customer(db: AsyncSession, organization_id: uuid.UUID, data: CustomerCreate) -> Customer:
    customer = Customer(
        organization_id=organization_id,
        full_name=data.full_name,
        phone=data.phone,
        notes=data.notes,
    )
    db.add(customer)
    await db.flush()
    return customer


async def update_customer(
    db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID, data: CustomerUpdate
) -> Customer:
    customer = await _get_scoped_customer(db, organization_id, customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"No customer {customer_id} in this organization")

    if data.full_name is not None:
        customer.full_name = data.full_name
    if data.phone is not None:
        customer.phone = data.phone
    if data.notes is not None:
        customer.notes = data.notes
    if data.is_active is not None:
        customer.is_active = data.is_active

    await db.flush()
    # updated_at (server-side onupdate=func.now()) comes back expired, not
    # populated, after an UPDATE under the async driver — see the same
    # comment in user_service.py. Without this, response serialization
    # would raise MissingGreenlet trying to lazy-load it.
    await db.refresh(customer)
    return customer


async def archive_customer(db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = await _get_scoped_customer(db, organization_id, customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"No customer {customer_id} in this organization")

    customer.is_active = False
    await db.flush()
    await db.refresh(customer)
    return customer


async def _get_scoped_customer(
    db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer | None:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    )
    return result.scalar_one_or_none()
