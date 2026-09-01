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
    # Not a persisted column — same gap, same fix as PhotoRead.view_url
    # (see that schema's own docstring): job_items_service attaches a
    # freshly generated, short-lived presigned GET URL at read time, since
    # `s3_key` alone is meaningless to a browser against a private bucket.
    download_url: str
