"""Pydantic v2 schemas for Payment (Milestone 13)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentUpsert(BaseModel):
    amount: Decimal = Field(gt=0)
    method: PaymentMethod
    status: PaymentStatus = PaymentStatus.UNPAID
    # Optional — lets a caller backdate to when payment was actually
    # received. If status=paid and this is omitted, the service fills in
    # now() per the roadmap ("setting status=paid without paid_at
    # auto-sets paid_at=now()").
    paid_at: datetime | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
