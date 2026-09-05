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

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.user import MeUpdate, UserCreate, UserUpdate
from app.storage import s3_client

# Mirrors job_items_service's own _EXTENSION_BY_CONTENT_TYPE — same
# accepted formats, kept as its own small mapping rather than imported
# since it belongs to an unrelated upload (a user's avatar, not a job
# photo) that just happens to accept the same file types today.
_AVATAR_EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}

# Matches exactly what generate_avatar_upload_url builds for a given user —
# `set_avatar` checks a submitted s3_key against this rather than trusting
# it outright. Without this, a client could confirm ANY key as their own
# avatar (another org's job photo, another user's document, ...) and
# attach_avatar_url would then hand back a valid presigned GET URL for
# it — an IDOR letting an authenticated user read arbitrary objects in the
# shared bucket, not just their own.
_AVATAR_KEY_PATTERN = re.compile(
    r"^(?P<organization_id>[0-9a-f-]{36})/users/(?P<user_id>[0-9a-f-]{36})/avatar/"
    r"[0-9a-f-]{36}\.(?:jpg|png|webp|heic)$"
)


def _is_own_avatar_key(user: User, s3_key: str) -> bool:
    match = _AVATAR_KEY_PATTERN.match(s3_key)
    if match is None:
        return False
    return match["organization_id"] == str(user.organization_id) and match["user_id"] == str(user.id)


class UserServiceError(Exception):
    """Base class for user-service failures the router maps to HTTP status codes."""


class UserNotFoundError(UserServiceError):
    pass


class CannotModifyOwnRoleError(UserServiceError):
    pass


class LastOwnerError(UserServiceError):
    pass


class InvalidCurrentPasswordError(UserServiceError):
    pass


class InvalidAvatarKeyError(UserServiceError):
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

    if data.password is not None:
        user.hashed_password = hash_password(data.password)

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


def attach_avatar_url(user: User) -> User:
    """
    Attaches a transient `avatar_url` (a freshly signed, short-lived GET
    URL) for MeRead's benefit — mirrors job_items_service's
    `_with_view_url` for photos exactly, including "not a persisted
    column" for the same reason: the bucket is private, so only the s3_key
    is ever stored, and a browser needs a real URL to render an <img> from.
    `None` when the user has no avatar yet, rather than signing a URL for
    a key that was never uploaded to.
    """
    user.avatar_url = (
        s3_client.generate_presigned_download_url(user.avatar_s3_key) if user.avatar_s3_key else None
    )
    return user


async def update_me(db: AsyncSession, user: User, data: MeUpdate) -> User:
    """
    A user editing their own profile (name/email/phone) — distinct from
    update_user above, which is the owner-only "manage someone else"
    path and only ever touches role/is_active. Raises the same
    IntegrityError update_user's caller (create_user) already handles
    when data.email collides with another user in the organization — left
    to propagate rather than caught here, so the router can map it to the
    same 409 create_user's does, instead of this function inventing a
    second translation of the same database constraint.
    """
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.email is not None:
        user.email = data.email
    if data.phone is not None:
        user.phone = data.phone or None

    await db.flush()
    await db.refresh(user)  # see the comment in update_user for why this is needed
    return attach_avatar_url(user)


async def change_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCurrentPasswordError("Current password is incorrect")

    user.hashed_password = hash_password(new_password)
    await db.flush()


def generate_avatar_upload_url(user: User, content_type: str) -> tuple[str, str]:
    extension = _AVATAR_EXTENSION_BY_CONTENT_TYPE[content_type]
    key = f"{user.organization_id}/users/{user.id}/avatar/{uuid.uuid4()}.{extension}"
    upload_url = s3_client.generate_presigned_upload_url(key, content_type)
    return upload_url, key


async def set_avatar(db: AsyncSession, user: User, s3_key: str) -> User:
    if not _is_own_avatar_key(user, s3_key):
        raise InvalidAvatarKeyError("This s3_key was not issued for this user's avatar")

    user.avatar_s3_key = s3_key
    await db.flush()
    await db.refresh(user)
    return attach_avatar_url(user)


async def clear_avatar(db: AsyncSession, user: User) -> User:
    user.avatar_s3_key = None
    await db.flush()
    await db.refresh(user)
    return attach_avatar_url(user)


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
