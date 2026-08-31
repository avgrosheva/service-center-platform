"""
User model (Milestone 3).

Any human who logs in — owner, dispatcher, or technician.

Role is a plain Python Enum enforced via SQLAlchemy Enum(native_enum=False),
per the frozen architecture decision (Prompt 2 refinements): this renders
as VARCHAR + CHECK constraint in Postgres rather than a native Postgres
enum type, so adding a new role later is a straightforward migration
instead of the more awkward ALTER TYPE ... ADD VALUE dance. Every other
status-like column across the app (job status, payment status, etc., from
their respective milestones) follows this same pattern.
"""

import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class UserRole(str, enum.Enum):
    OWNER = "owner"
    DISPATCHER = "dispatcher"
    TECHNICIAN = "technician"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_organization_email"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(nullable=False)
    hashed_password: Mapped[str] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="ck_users_role",
            native_enum=False,
            validate_strings=True,
            length=20,
            # SQLAlchemy's Enum(native_enum=False) does NOT create a CHECK
            # constraint by default — create_constraint must be set
            # explicitly, or the "database-level enforcement" half of the
            # frozen architecture decision silently doesn't happen and role
            # is validated in Python only. This was caught by
            # test_invalid_role_rejected_at_database_level, which inserts
            # via raw SQL (bypassing the ORM's own validation) specifically
            # to prove the database itself rejects an invalid value.
            create_constraint=True,
            # By default SQLAlchemy's Enum type stores the Python member's
            # .name (e.g. "OWNER") in the database, not its .value (e.g.
            # "owner"). Since UserRole's values are the lowercase strings
            # used throughout the Product Definition and API, values_callable
            # makes the column store/compare those lowercase values instead
            # — otherwise the DB would silently contain "OWNER" while the
            # rest of the app talks about "owner".
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)