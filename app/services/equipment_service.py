"""
Equipment management business logic (Milestone 7).

Follows the tenant-scoping convention established in Milestones 5-6:
organization_id always comes from current_user (never client input), every
query filters by it, and an equipment_id (or customer_id) belonging to
another organization is treated exactly like one that doesn't exist
(EquipmentNotFoundError / CustomerNotFoundError -> 404 in the router).

Equipment always belongs to a customer, so every entry point here (list,
create) is also handed a customer_id and must confirm that customer exists
*in the caller's organization* before doing anything else — this is what
rejects "create equipment under a customer from a different org" even when
the customer_id itself is well-formed and exists in the database, just not
in this tenant.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.equipment import Equipment
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate


class EquipmentServiceError(Exception):
    """Base class for equipment-service failures the router maps to HTTP status codes."""


class EquipmentNotFoundError(EquipmentServiceError):
    pass


class CustomerNotFoundError(EquipmentServiceError):
    """Raised when the customer_id a request scopes equipment to doesn't exist in this org."""


async def _get_scoped_customer(db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer | None:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def _require_scoped_customer(db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = await _get_scoped_customer(db, organization_id, customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"No customer {customer_id} in this organization")
    return customer


async def list_equipment_for_customer(
    db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID
) -> list[Equipment]:
    await _require_scoped_customer(db, organization_id, customer_id)

    result = await db.execute(
        select(Equipment)
        .where(Equipment.organization_id == organization_id, Equipment.customer_id == customer_id)
        .order_by(Equipment.created_at)
    )
    return list(result.scalars().all())


async def create_equipment(
    db: AsyncSession, organization_id: uuid.UUID, customer_id: uuid.UUID, data: EquipmentCreate
) -> Equipment:
    await _require_scoped_customer(db, organization_id, customer_id)

    equipment = Equipment(
        organization_id=organization_id,
        customer_id=customer_id,
        type=data.type,
        brand=data.brand,
        model=data.model,
        serial_number=data.serial_number,
        installation_address=data.installation_address,
        install_date=data.install_date,
        warranty_until=data.warranty_until,
    )
    db.add(equipment)
    await db.flush()
    return equipment


async def get_equipment(db: AsyncSession, organization_id: uuid.UUID, equipment_id: uuid.UUID) -> Equipment:
    equipment = await _get_scoped_equipment(db, organization_id, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError(f"No equipment {equipment_id} in this organization")
    return equipment


async def update_equipment(
    db: AsyncSession, organization_id: uuid.UUID, equipment_id: uuid.UUID, data: EquipmentUpdate
) -> Equipment:
    equipment = await _get_scoped_equipment(db, organization_id, equipment_id)
    if equipment is None:
        raise EquipmentNotFoundError(f"No equipment {equipment_id} in this organization")

    if data.type is not None:
        equipment.type = data.type
    if data.brand is not None:
        equipment.brand = data.brand
    if data.model is not None:
        equipment.model = data.model
    if data.serial_number is not None:
        equipment.serial_number = data.serial_number
    if data.installation_address is not None:
        # This is the one field with a documented invariant elsewhere: per
        # the frozen address model, changing it here must never reach back
        # and alter `jobs.address_snapshot` on any job already created
        # against this equipment. That guarantee is enforced (and tested)
        # in job_service.py from Milestone 8 onward — there is deliberately
        # no snapshot/versioning logic on this model itself, since
        # `jobs.address_snapshot` is a one-time copy taken at job-creation
        # time, not a reference back to this row.
        equipment.installation_address = data.installation_address
    if data.install_date is not None:
        equipment.install_date = data.install_date
    if data.warranty_until is not None:
        equipment.warranty_until = data.warranty_until

    await db.flush()
    # updated_at (server-side onupdate=func.now()) comes back expired, not
    # populated, after an UPDATE under the async driver — see the same
    # comment in user_service.py / customer_service.py.
    await db.refresh(equipment)
    return equipment


async def _get_scoped_equipment(
    db: AsyncSession, organization_id: uuid.UUID, equipment_id: uuid.UUID
) -> Equipment | None:
    result = await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, Equipment.organization_id == organization_id)
    )
    return result.scalar_one_or_none()
