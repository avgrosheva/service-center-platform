"""Pydantic v2 schemas for AdditionalWorkItem (Milestone 12)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.additional_work_item import AdditionalWorkStatus


class AdditionalWorkItemCreate(BaseModel):
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0)


class AdditionalWorkItemStatusUpdate(BaseModel):
    # Only status transitions via PATCH per the roadmap ("Change status:
    # approve/reject/mark billed") — description/price aren't editable
    # after flagging.
    status: AdditionalWorkStatus


class AdditionalWorkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    description: str
    price: Decimal
    status: AdditionalWorkStatus
    created_by_id: uuid.UUID
    created_at: datetime
