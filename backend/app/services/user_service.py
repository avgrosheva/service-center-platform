"""
User management business logic (Milestone 5).

Every function here takes organization_id explicitly — always derived from
current_user in the router, never from client input — and every query
filters by it. This is the tenant-isolation convention every future
*_service.py module follows (per the Technical Blueprint's Section 6): a
user_id belonging to a different organization is treated exactly like a
user_id that doesn't exist at all (a service-level UserNotFoundError, which
the router maps to 404), so a request can never be used to distinguish
"doesn't exist" from "exists in someone else's organization."
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate


class UserServiceError(Exception):
    """Base class for user-service failures the router maps to HTTP status codes."""


class UserNotFoundError(UserServiceError):
    pass


class CannotModifyOwnRoleError(UserServiceError):
    pass


class LastOwnerError(UserServiceError):
    pass


async def list_users(db: AsyncSession, organization_id: uuid.UUID) -> list[User]:
    result = await db.execute(
        select(User).where(User.organization_id == organization_id).order_by(User.created_at)
    )
    return list(result.scalars().all())


async def get_user(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = await _get_scoped_user(db, organization_id, user_id)
    if user is None:
        raise UserNotFoundError(f"No user {user_id} in this organization")
    return user


async def create_user(db: AsyncSession, organization_id: uuid.UUID, data: UserCreate) -> User:
    user = User(
        organization_id=organization_id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.flush()
    return user


async def update_user(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    data: UserUpdate,
    current_user: User,
) -> User:
    user = await _get_scoped_user(db, organization_id, user_id)
    if user is None:
        raise UserNotFoundError(f"No user {user_id} in this organization")

    if data.role is not None and data.role != user.role:
        if user.id == current_user.id:
            raise CannotModifyOwnRoleError("A user cannot change their own role")
        # No _guard_last_owner call needed here: this endpoint requires the
        # caller to be an active owner (require_role(OWNER)), and the
        # self-role-change case is already excluded above — so whenever
        # this line runs, current_user is a *different*, still-active
        # owner, which means at least one owner (current_user) always
        # survives the change regardless of the target's new role.
        user.role = data.role

    if data.is_active is not None and data.is_active != user.is_active:
        if data.is_active is False and user.role == UserRole.OWNER:
            await _guard_last_owner(db, organization_id, excluding_user_id=user.id)
        user.is_active = data.is_active

    await db.flush()
    # updated_at (server-side onupdate=func.now()) comes back expired, not
    # populated, after an UPDATE flush under the async driver — unlike an
    # INSERT, which gets it via RETURNING automatically. Without this
    # explicit refresh, FastAPI's response serialization (which runs
    # outside any awaited context) tries to lazy-load it and raises
    # MissingGreenlet instead of a clean response.
    await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = await _get_scoped_user(db, organization_id, user_id)
    if user is None:
        raise UserNotFoundError(f"No user {user_id} in this organization")

    if user.is_active and user.role == UserRole.OWNER:
        await _guard_last_owner(db, organization_id, excluding_user_id=user.id)

    user.is_active = False
    await db.flush()
    await db.refresh(user)  # see the comment in update_user for why this is needed
    return user


async def _get_scoped_user(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def _guard_last_owner(
    db: AsyncSession, organization_id: uuid.UUID, *, excluding_user_id: uuid.UUID
) -> None:
    """
    Raises LastOwnerError if the change being made to excluding_user_id
    (a role change away from owner, or a deactivation) would leave the
    organization with zero remaining active owners.
    """
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.organization_id == organization_id,
            User.role == UserRole.OWNER,
            User.is_active.is_(True),
            User.id != excluding_user_id,
        )
    )
    remaining_owners = result.scalar_one()
    if remaining_owners == 0:
        raise LastOwnerError("Cannot remove the last remaining owner of an organization")
