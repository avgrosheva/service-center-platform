"""
Organization model (Milestone 3).

The tenant boundary — every other domain entity (customers, equipment,
jobs, etc., added in later milestones) belongs to exactly one organization
via an organization_id foreign key.
"""

from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(nullable=False)