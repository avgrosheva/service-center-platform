"""
Tests for Milestone 3's Organization and User models/migration.

These run against the real (already-migrated) database rather than a
scratch table, since the whole point of this milestone is proving the
actual organizations/users tables and their constraints work — the unique
constraint and the CHECK constraint on `role` are DB-level guarantees, not
just Python-level ones, so they need a real database to verify.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.models import Organization, User, UserRole


async def _make_org(session, name="Test Org") -> Organization:
    org = Organization(name=name)
    session.add(org)
    await session.flush()
    return org


@pytest.mark.asyncio
async def test_create_organization_and_user():
    async with AsyncSessionLocal() as session:
        org = await _make_org(session, name="Acme Repairs")
        user = User(
            organization_id=org.id,
            email="owner@acme.test",
            hashed_password="not-a-real-hash",
            full_name="Ada Owner",
            role=UserRole.OWNER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert isinstance(user.id, uuid.UUID)
        assert user.organization_id == org.id
        assert user.role == UserRole.OWNER
        assert user.is_active is True  # default


@pytest.mark.asyncio
async def test_duplicate_email_within_same_organization_is_rejected():
    async with AsyncSessionLocal() as session:
        org = await _make_org(session, name="Duplicate Email Org")
        session.add(User(
            organization_id=org.id,
            email="dupe@example.test",
            hashed_password="hash1",
            full_name="First User",
            role=UserRole.DISPATCHER,
        ))
        await session.commit()

    async with AsyncSessionLocal() as session:
        session.add(User(
            organization_id=org.id,
            email="dupe@example.test",
            hashed_password="hash2",
            full_name="Second User",
            role=UserRole.TECHNICIAN,
        ))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_same_email_allowed_across_different_organizations():
    async with AsyncSessionLocal() as session:
        org_a = await _make_org(session, name="Org A")
        org_b = await _make_org(session, name="Org B")

        session.add(User(
            organization_id=org_a.id,
            email="shared@example.test",
            hashed_password="hash1",
            full_name="User In Org A",
            role=UserRole.OWNER,
        ))
        session.add(User(
            organization_id=org_b.id,
            email="shared@example.test",
            hashed_password="hash2",
            full_name="User In Org B",
            role=UserRole.OWNER,
        ))
        # Should NOT raise — same email, different organizations.
        await session.commit()


@pytest.mark.asyncio
async def test_invalid_role_rejected_at_database_level():
    """
    Proves the CHECK constraint exists in the database itself, independent
    of the ORM. The SQLAlchemy Enum type would normally stop an invalid
    Python-level value before it ever reaches the database, so this uses
    raw SQL to bypass the ORM's own validation and confirm the database
    would reject it too (e.g. if a row were ever inserted by a manual
    script or a future migration bug).
    """
    async with AsyncSessionLocal() as session:
        org = await _make_org(session, name="Invalid Role Org")
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO users
                        (id, organization_id, email, hashed_password, full_name, role, is_active, created_at, updated_at)
                    VALUES
                        (gen_random_uuid(), :org_id, 'bad-role@example.test', 'x', 'Bad Role', 'not_a_real_role', true, now(), now())
                    """
                ),
                {"org_id": org.id},
            )
            await session.commit()