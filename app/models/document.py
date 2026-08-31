"""
Document model (Milestone 14) — a generated PDF (job report / repair
certificate) tied to a job.

No `updated_at`, matching Section 3's explicit column list exactly (id,
job_id, type, s3_key, generated_at): documents are immutable once
generated — the API table only defines POST/GET, no PATCH/DELETE — so
`generated_at` alone is the complete timestamp story, same reasoning as
`photos`.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentType(str, enum.Enum):
    JOB_REPORT = "job_report"
    REPAIR_CERTIFICATE = "repair_certificate"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[DocumentType] = mapped_column(
        SAEnum(
            DocumentType,
            name="ck_documents_type",
            native_enum=False,
            validate_strings=True,
            length=30,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
