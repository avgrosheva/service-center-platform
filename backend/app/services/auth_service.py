"""
Auth business logic (Milestone 4): register, login, refresh.

Routers stay thin — they parse the request and translate the exceptions
raised here into HTTP status codes. Keeping the actual logic here (rather
than in app/routers/auth.py) is what makes it testable without going
through the ASGI layer.
"""

import uuid

import jwt as pyjwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest, TokenResponse


class AuthError(Exception):
    """Base class for auth failures the router maps to HTTP status codes."""


class InvalidCredentialsError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


def _issue_tokens(user: User, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, organization_id=user.organization_id, role=user.role, settings=settings
        ),
        refresh_token=create_refresh_token(
            user_id=user.id, organization_id=user.organization_id, role=user.role, settings=settings
        ),
    )


async def register(db: AsyncSession, data: RegisterRequest, settings: Settings) -> TokenResponse:
    """
    Creates an organization and its owner user together. Both inserts ride
    the same session/transaction that app.database.get_db manages — flush
    (not commit) here so the organization's generated id is available for
    the user's FK without ending the transaction; get_db commits both rows
    atomically once the request handler returns successfully, or rolls
    both back on any exception.
    """
    organization = Organization(name=data.organization_name)
    db.add(organization)
    await db.flush()

    user = User(
        organization_id=organization.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.flush()

    return _issue_tokens(user, settings)


async def login(db: AsyncSession, email: str, password: str, settings: Settings) -> TokenResponse:
    # Email is only unique *within* an organization (Milestone 3), so the
    # same email can legitimately belong to a different user in a different
    # org. Login is org-less by design (per the documented API surface —
    # just email + password), so every matching row is checked against the
    # supplied password rather than assuming the email is globally unique.
    #
    # If more than one candidate's password matches — same email *and* same
    # password reused across two different organizations — `next()` below
    # would otherwise resolve to whichever row Postgres happened to return
    # first, which is undefined without an ORDER BY. Ordering by
    # (created_at, id) makes that pick deterministic: the account that
    # registered first always wins. This is a tie-break rule, not a
    # security boundary — a real collision here is a rare coincidence, not
    # an attack, since it requires already knowing both the email and the
    # correct password for one specific account.
    result = await db.execute(select(User).where(User.email == email).order_by(User.created_at, User.id))
    candidates = result.scalars().all()

    user = next((u for u in candidates if verify_password(password, u.hashed_password)), None)
    if user is None:
        raise InvalidCredentialsError("Invalid email or password")
    if not user.is_active:
        raise InactiveUserError("This account has been deactivated")

    return _issue_tokens(user, settings)


async def refresh_access_token(db: AsyncSession, refresh_token: str, settings: Settings) -> str:
    try:
        payload = decode_token(refresh_token, settings)
    except pyjwt.PyJWTError as exc:
        raise InvalidTokenError("Invalid or expired refresh token") from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise InvalidTokenError("Token is not a refresh token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Malformed token payload") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("User no longer exists or is inactive")

    return create_access_token(
        user_id=user.id, organization_id=user.organization_id, role=user.role, settings=settings
    )
