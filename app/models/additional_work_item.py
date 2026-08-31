"""
AdditionalWorkItem model (Milestone 12) — extra work discovered on-site
that needs owner/dispatcher approval and billing.

`organization_id` is denormalized here directly (rather than reached only
via a join through `jobs`) per the roadmap's own explicit call-out for
this milestone: it backs the `(organization_id, status)` index this table
needs for the "unbilled additional work" dashboard metric (Milestone 16)
and the Product Definition's "% of jobs with additional work" / "% billed
vs unbilled" success metrics. It's set once at creation from the parent
job's organization_id and never changes, so there's no sync-drift risk.

No `updated_at`, matching `material_items`' precedent: this row is
mutated (status transitions via PATCH), but the append-only
`job_status_history` timeline is the authoritative record of *when* and
*by whom* each transition happened, not a timestamp on this row.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdditionalWorkStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BILLED = "billed"


class AdditionalWorkItem(Base):
    __tablename__ = "additional_work_items"
    __table_args__ = (
        Index("ix_additional_work_items_organization_id_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[AdditionalWorkStatus] = mapped_column(
        SAEnum(
            AdditionalWorkStatus,
            name="ck_additional_work_items_status",
            native_enum=False,
            validate_strings=True,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=AdditionalWorkStatus.PENDING,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
