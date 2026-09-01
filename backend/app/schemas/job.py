"""Pydantic v2 schemas for Job (Milestone 8)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.job import JobStatus


class JobCreate(BaseModel):
    customer_id: uuid.UUID
    equipment_id: uuid.UUID | None = None
    reported_issue: str = Field(min_length=1)
    # Raw address input, used only when no equipment_id is given. When
    # equipment_id IS given, the service always derives address_snapshot
    # from that equipment's current installation_address and ignores this
    # field entirely — per the frozen address model, the snapshot must come
    # from one authoritative source, not from whichever the client happens
    # to send.
    address: str | None = None
    scheduled_at: datetime | None = None
    # Milestone 15: the auto-flagging rule (a still-under-warranty prior
    # completed job on the same equipment) only ever *suggests* a value —
    # "never fully lock the field" per the roadmap. None means "let
    # auto-detection decide"; an explicit True/False always overrides it.
    is_warranty_claim: bool | None = None

    @model_validator(mode="after")
    def _address_required_without_equipment(self) -> "JobCreate":
        if self.equipment_id is None and not (self.address and self.address.strip()):
            raise ValueError("address is required when no equipment_id is provided")
        return self


class JobUpdate(BaseModel):
    # Status changes are deliberately excluded here — that's Milestone 9's
    # validated state machine, not a plain field edit.
    reported_issue: str | None = Field(default=None, min_length=1)
    address_snapshot: str | None = Field(default=None, min_length=1)
    scheduled_at: datetime | None = None


class JobAssignRequest(BaseModel):
    technician_id: uuid.UUID


class JobStatusChangeRequest(BaseModel):
    status: JobStatus
    note: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    equipment_id: uuid.UUID | None
    assigned_technician_id: uuid.UUID | None
    created_by_id: uuid.UUID
    status: JobStatus
    reported_issue: str
    address_snapshot: str
    scheduled_at: datetime | None
    completed_at: datetime | None
    is_warranty_claim: bool
    origin_job_id: uuid.UUID | None
    warranty_expires_at: date | None
    created_at: datetime
    updated_at: datetime
