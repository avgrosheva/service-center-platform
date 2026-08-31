"""
Photo model (Milestone 10) — field evidence attached to a job.

No `updated_at`: like `job_status_history`, this table is effectively
append-only for the MVP. The Technical Blueprint's API table only defines
POST/GET for photos (no PATCH/DELETE), so nothing here is ever edited
after creation.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PhotoTag(str, enum.Enum):
    BEFORE = "before"
    AFTER = "after"
    GENERAL = "general"


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    s3_key: Mapped[str] = mapped_column(nullable=False)
    tag: Mapped[PhotoTag | None] = mapped_column(
        SAEnum(
            PhotoTag,
            name="ck_photos_tag",
            native_enum=False,
            validate_strings=True,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
