"""Pydantic v2 schemas for Equipment (Milestone 7)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EquipmentBase(BaseModel):
    type: str = Field(min_length=1)
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    installation_address: str = Field(min_length=1)
    install_date: date | None = None
    warranty_until: date | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1)
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    installation_address: str | None = Field(default=None, min_length=1)
    install_date: date | None = None
    warranty_until: date | None = None


class EquipmentRead(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
