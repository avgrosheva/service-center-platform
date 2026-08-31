"""
JobStatusHistory model (Milestone 9) — the append-only activity timeline.

Every status transition (via `/jobs/{id}/status`), every assignment (via
`/jobs/{id}/assign`), and every sub-resource added to a job (a photo via
Milestone 10, materials/additional-work/documents in Milestones 11-14)
writes exactly one row here; rows are never updated or deleted. Unlike
`models/job.py`'s `status` column, `event_type` is intentionally a plain
string with no CHECK constraint: the roadmap adds new event types
milestone by milestone as unrelated modules land sub-resources on a job,
and DB-enforcing that growing set here would force a migration on every
one of those future milestones for no safety benefit job_service.py /
job_items_service.py don't already provide by only ever writing known
constants. `JobEventType` below is the Python-side source of truth for
the event types introduced so far.

`from_status`/`to_status`, by contrast, ARE DB-enforced via the same
`JobStatus` enum `models/job.py` uses for `jobs.status` — that set is
closed and already has a change-control process (the state machine in
job_service.py), so the same enum applies here too.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.job import JobStatus


class JobEventType(str, enum.Enum):
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    PHOTO_ADDED = "photo_added"
    MATERIAL_ADDED = "material_added"
    MATERIAL_EDITED = "material_edited"
    MATERIAL_REMOVED = "material_removed"
    ADDITIONAL_WORK_FLAGGED = "additional_work_flagged"
    ADDITIONAL_WORK_APPROVED = "additional_work_approved"
    ADDITIONAL_WORK_REJECTED = "additional_work_rejected"
    ADDITIONAL_WORK_BILLED = "additional_work_billed"
    DOCUMENT_GENERATED = "document_generated"


def _job_status_enum(column_name: str) -> SAEnum:
    # Each use needs its own constraint name — reusing one across two
    # columns on the same table would collide on the CHECK constraint name
    # at the database level.
    return SAEnum(
        JobStatus,
        name=f"ck_job_status_history_{column_name}",
        native_enum=False,
        validate_strings=True,
        length=20,
        create_constraint=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class JobStatusHistory(Base):
    __tablename__ = "job_status_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable: a future system-generated entry (e.g. the Milestone 15
    # warranty-check scheduled task) has no human actor.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(nullable=False)
    from_status: Mapped[JobStatus | None] = mapped_column(_job_status_enum("from_status"), nullable=True)
    to_status: Mapped[JobStatus | None] = mapped_column(_job_status_enum("to_status"), nullable=True)
    note: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
