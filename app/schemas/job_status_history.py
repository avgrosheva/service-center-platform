"""Pydantic v2 schema for JobStatusHistory (Milestone 9)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus


class JobStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: str
    from_status: JobStatus | None
    to_status: JobStatus | None
    note: str | None
    created_at: datetime
