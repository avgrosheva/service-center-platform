"""
Async SQLAlchemy engine, session factory, and declarative Base (Milestone 2).

This is the one place that owns:
- the async engine (created once, reused for the lifetime of the process)
- a per-request AsyncSession, handed out via the `get_db` FastAPI dependency
- the shared declarative Base + a TimestampMixin all domain models inherit from

Nothing outside this module should call create_async_engine() or
async_sessionmaker() directly.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

settings = get_settings()

# echo=True (via environment==development) is useful for seeing generated
# SQL while developing; this should never be true in production, which is
# why it's tied to settings.environment rather than a separate flag that
# could be forgotten.
engine = create_async_engine(
    settings.database_url,
    echo=(settings.environment == "development"),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base. Every ORM model (from Milestone 3 onward) inherits from this."""


class TimestampMixin:
    """
    Adds id / created_at / updated_at to any model that inherits it.

    id: UUID primary key generated in Python (uuid.uuid4), not via a
    Postgres extension like gen_random_uuid() — keeps model behavior
    identical across environments without depending on pgcrypto/uuid-ossp
    being enabled on the database.

    created_at / updated_at: set by the database itself (server_default /
    onupdate using func.now()), not by application code. This avoids
    clock-skew issues between app instances and guarantees both columns
    are populated even for rows inserted outside the ORM.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


async def get_db():
    """
    FastAPI dependency yielding a request-scoped AsyncSession.

    Commits on clean exit, rolls back on any unhandled exception, always
    closes the session. Routers/services should depend on this rather than
    instantiating a session directly.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()