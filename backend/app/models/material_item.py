"""
MaterialItem model (Milestone 11) — a part/material used on a job.

Purely a flat line-item log per the frozen architecture (Technical
Blueprint, Section 3: "No inventory/stock table") — not linked to any
stock ledger. No `total` column: quantity * unit_cost is computed by
callers when needed, not persisted — Section 3's Database Design table
(the authoritative schema, same resolution used for Equipment/Photo in
earlier milestones) doesn't list one, even though Section 2's looser
narrative description mentions "total" in passing.

No `updated_at` either, matching Section 3 exactly, even though this row
is editable via PATCH: the append-only `job_status_history` timeline is
the edit record, not a mutated timestamp on this row.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MaterialItem(Base):
    __tablename__ = "material_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
