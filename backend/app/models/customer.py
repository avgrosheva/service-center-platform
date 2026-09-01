"""
Customer model (Milestone 6).

The person/business being served. Carries no address field of its own —
per the frozen address model (Technical Blueprint, Section 3), a
customer's service locations live on their equipment records instead,
since one customer can have equipment at multiple sites. Soft-delete only
(`is_active`): a customer with job history must never be hard-deleted.
"""

import uuid

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        # Composite, not just organization_id alone: phone lookup/dedup
        # (per the Technical Blueprint) always happens within one caller's
        # organization, never globally across tenants.
        Index("ix_customers_organization_id_phone", "organization_id", "phone"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(nullable=False)
    phone: Mapped[str] = mapped_column(nullable=False)
    notes: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
