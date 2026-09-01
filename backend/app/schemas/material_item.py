"""Pydantic v2 schemas for MaterialItem (Milestone 11)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MaterialItemCreate(BaseModel):
    name: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class MaterialItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class MaterialItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    name: str
    quantity: Decimal
    unit_cost: Decimal | None
    created_at: datetime
