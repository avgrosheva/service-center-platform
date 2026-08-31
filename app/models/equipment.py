"""
Equipment model (Milestone 7).

The physical unit being repaired (AC unit, fridge, boiler, etc.), linked to
a Customer. Per the frozen address model (Technical Blueprint, Section 3),
`installation_address` here is the current, canonical address — a plain,
freely-editable text field. It is deliberately NOT the historical record of
where a given job was performed: that's `jobs.address_snapshot`, a copy
taken at job-creation time (Milestone 8), which must stay unchanged when
this field is later edited. Nothing about that invariant lives on this
model — it's enforced entirely in `job_service.py` when Jobs exist — but
keeping `installation_address` an ordinary mutable column (no versioning,
no read-only-after-create behavior) here is what keeps that guarantee easy
to implement later without reshaping this table.
"""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Equipment(Base, TimestampMixin):
    __tablename__ = "equipment"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(nullable=False)
    brand: Mapped[str | None] = mapped_column(nullable=True)
    model: Mapped[str | None] = mapped_column(nullable=True)
    # No uniqueness constraint per the roadmap: not every business tracks
    # reliable serial numbers, and blocking on it would reject valid data.
    serial_number: Mapped[str | None] = mapped_column(nullable=True)
    installation_address: Mapped[str] = mapped_column(nullable=False)
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)
