"""
Tests for Milestone 2's database infrastructure.

Uses a throwaway test-only model (not part of app/models, which stays
empty until Milestone 3) to exercise TimestampMixin and the get_db session
behavior against a real database.

Note on testing get_db's rollback behavior: FastAPI drives a generator
dependency by entering it as an async context manager (via
contextlib.AsyncExitStack), so an exception raised inside the route handler
is thrown *into* the generator at its yield point, triggering get_db's
`except Exception: await session.rollback()` block. A plain `async for
session in get_db(): ...` loop does NOT do this — an exception raised in
the loop body just propagates in the caller's frame without ever being
thrown into the generator, so the rollback code would never actually run
and the test would pass for the wrong reason. Wrapping get_db with
contextlib.asynccontextmanager reproduces FastAPI's real behavior.
"""

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import AsyncSessionLocal, Base, TimestampMixin, engine, get_db

db_context = asynccontextmanager(get_db)


class _ScratchThing(Base, TimestampMixin):
    """Test-only table, created/dropped around each test in this module."""

    __tablename__ = "_scratch_things_for_milestone_2_tests"

    name: Mapped[str] = mapped_column(String, nullable=False)


@pytest.fixture(autouse=True)
async def _create_and_drop_scratch_table():
    # Cross-event-loop connection reuse (see the _dispose_engine_between_tests
    # fixture in conftest.py) is handled centrally now — this fixture just
    # owns creating/dropping the scratch table around each test.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[_ScratchThing.__table__])
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=[_ScratchThing.__table__])


@pytest.mark.asyncio
async def test_timestamp_mixin_populates_id_and_timestamps():
    async with AsyncSessionLocal() as session:
        thing = _ScratchThing(name="widget")
        session.add(thing)
        await session.commit()
        await session.refresh(thing)

        assert isinstance(thing.id, uuid.UUID)
        assert thing.created_at is not None
        assert thing.updated_at is not None
        assert thing.created_at == thing.updated_at  # both set together on insert


@pytest.mark.asyncio
async def test_updated_at_changes_on_update():
    async with AsyncSessionLocal() as session:
        thing = _ScratchThing(name="widget-2")
        session.add(thing)
        await session.commit()
        await session.refresh(thing)
        original_updated_at = thing.updated_at

        thing.name = "widget-2-renamed"
        await session.commit()
        await session.refresh(thing)

        assert thing.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_get_db_commits_on_success():
    async with db_context() as session:
        thing = _ScratchThing(name="committed-thing")
        session.add(thing)
        await session.flush()
        thing_id = thing.id

    async with AsyncSessionLocal() as verify_session:
        result = await verify_session.get(_ScratchThing, thing_id)
        assert result is not None
        assert result.name == "committed-thing"


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception():
    thing_id = None

    with pytest.raises(RuntimeError):
        async with db_context() as session:
            thing = _ScratchThing(name="should-not-persist")
            session.add(thing)
            await session.flush()
            thing_id = thing.id
            raise RuntimeError("simulated failure mid-request")

    async with AsyncSessionLocal() as verify_session:
        result = await verify_session.get(_ScratchThing, thing_id)
        assert result is None