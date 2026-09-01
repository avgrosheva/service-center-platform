"""
Job model (Milestone 8) — Job only; JobStatusHistory (the append-only
timeline) lands in Milestone 9, along with validated status transitions
and full technician "own jobs only" scoping.

`address_snapshot` is the frozen half of the address model (Technical
Blueprint, Section 3): a one-time copy of `equipment.installation_address`
taken at job-creation time (or supplied directly when no equipment is
linked). It is never re-derived — a later edit to the equipment's own
`installation_address` must not reach back and change this value on any
job already created against that equipment. That invariant lives entirely
in `job_service.create_job` (the only place this column is ever written in
Milestone 8) and is proven by
`test_jobs.py::test_updating_equipment_address_does_not_retroactively_change_existing_job_snapshot`.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    IN_PROGRESS = "in_progress"
    AWAITING_PARTS = "awaiting_parts"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        # Per the Technical Blueprint's Section 3 index list: the two
        # composite indexes back the list endpoint's status/technician
        # filters, scheduled_at alone backs the delayed-job / date-range
        # query the Milestone 16 dashboard will build on.
        Index("ix_jobs_organization_id_status", "organization_id", "status"),
        Index("ix_jobs_organization_id_assigned_technician_id", "organization_id", "assigned_technician_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable per the domain model: a job can be created without a
    # pre-registered equipment record (address entered inline instead).
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_technician_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus,
            name="ck_jobs_status",
            native_enum=False,
            validate_strings=True,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=JobStatus.NEW,
    )
    reported_issue: Mapped[str] = mapped_column(nullable=False)
    address_snapshot: Mapped[str] = mapped_column(nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_warranty_claim: Mapped[bool] = mapped_column(default=False, nullable=False)
    origin_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    warranty_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
