"""Pydantic v2 schemas for Photo (Milestone 10)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.photo import PhotoTag

# Kept intentionally small and MVP-appropriate — the formats a phone
# camera actually produces. Anything else is rejected with a 422 at
# request-validation time, before a presigned URL is ever generated.
PhotoContentType = Literal["image/jpeg", "image/png", "image/webp", "image/heic"]


class PhotoUploadURLRequest(BaseModel):
    content_type: PhotoContentType


class PhotoUploadURLResponse(BaseModel):
    upload_url: str
    s3_key: str


class PhotoCreate(BaseModel):
    s3_key: str
    tag: PhotoTag | None = None


class PhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    uploaded_by_id: uuid.UUID
    s3_key: str
    tag: PhotoTag | None
    created_at: datetime
