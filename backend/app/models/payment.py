"""
Payment model (Milestone 13) — lightweight payment status tracking, one
per job. Enforced via a unique constraint on `job_id` rather than modeled
as one-to-many, per the frozen architecture ("one-to-one is sufficient for
MVP; model as one-to-many only if partial payments become a real need").

Unlike the other job sub-resources (photos, materials, additional work),
nothing here writes to `job_status_history` — Milestone 13's business
logic doesn't call for a timeline entry on payment changes, so none is
invented. That's exactly why, unlike `material_items`/
`additional_work_items` (which lean on the timeline as their edit record
and skip `updated_at`), this model keeps `updated_at` via `TimestampMixin`
— it's the only record of when a payment was last changed.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


class PaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(
            PaymentMethod,
            name="ck_payments_method",
            native_enum=False,
            validate_strings=True,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            name="ck_payments_status",
            native_enum=False,
            validate_strings=True,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PaymentStatus.UNPAID,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
