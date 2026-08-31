"""Pydantic v2 schemas for Document (Milestone 14)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentType


class DocumentGenerateRequest(BaseModel):
    type: DocumentType = DocumentType.JOB_REPORT


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    type: DocumentType
    s3_key: str
    generated_at: datetime
