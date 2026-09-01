"""
AITask model (Milestone 18) — tracks one async AI job so the frontend can
poll its status.

Every `/ai/*` endpoint creates exactly one row here (`status=pending`) and
returns immediately; `workers/ai_tasks.py` is the only code that ever
transitions it to `processing`, then `done`/`failed`. Per the roadmap's
hard rule (carried from the Product Definition): AI never writes directly
to a Job's core state (status, additional work, payment) — the only table
this model's own row ever touches is `ai_tasks` itself. Suggestions live
in `output` as plain text for a human to read and act on manually; nothing
in this codebase auto-creates an AdditionalWorkItem, changes a Job, or
touches a Payment from an AI task's result.

`organization_id` is required (every task belongs to exactly one tenant);
`job_id` is nullable, since `/ai/query` is a free-text question over the
whole organization's history, not scoped to one job.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AITaskType(str, enum.Enum):
    VOICE_TRANSCRIPTION = "voice_transcription"
    SUMMARY = "summary"
    ADDITIONAL_WORK_SUGGESTION = "additional_work_suggestion"
    QA_QUERY = "qa_query"


class AITaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


def _ai_task_enum(python_enum: type[enum.Enum], name: str, length: int) -> SAEnum:
    return SAEnum(
        python_enum,
        name=name,
        native_enum=False,
        validate_strings=True,
        length=length,
        create_constraint=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class AITask(Base):
    __tablename__ = "ai_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    task_type: Mapped[AITaskType] = mapped_column(
        _ai_task_enum(AITaskType, "ck_ai_tasks_task_type", 30), nullable=False
    )
    status: Mapped[AITaskStatus] = mapped_column(
        _ai_task_enum(AITaskStatus, "ck_ai_tasks_status", 20), nullable=False, default=AITaskStatus.PENDING
    )
    # Free-form: an S3 key for a voice note, a job_id restated as text for
    # summary/suggestion tasks, or the raw query string for Q&A — shape
    # depends on task_type, same "one polymorphic text column" pattern the
    # roadmap's own schema table specifies.
    input_ref: Mapped[str] = mapped_column(nullable=False)
    output: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
