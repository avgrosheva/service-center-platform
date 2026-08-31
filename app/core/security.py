"""
Password hashing and JWT encode/decode helpers (Milestone 4).

Deliberately stateless and DB-free — nothing here looks up a user. Anything
that needs the database (login, refresh, get_current_user) lives in
auth_service.py / dependencies.py instead, which keeps this module trivial
to unit test and reason about in isolation.
"""

import enum
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import Settings
from app.models.user import UserRole

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, enum.Enum):
    """
    Distinguishes access from refresh tokens inside the JWT payload itself
    (a "type" claim), so a refresh token can't be replayed as an access
    token (or vice versa) even though both are signed with the same secret.
    """

    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role: UserRole,
    token_type: TokenType,
    expires_delta: timedelta,
    settings: Settings,
) -> str:
    # user_id/organization_id/role ride along in every token (per the
    # frozen architecture) so downstream tenant scoping doesn't need an
    # extra DB round trip just to know which organization a request
    # belongs to.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "organization_id": str(organization_id),
        "role": role.value,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    *, user_id: uuid.UUID, organization_id: uuid.UUID, role: UserRole, settings: Settings
) -> str:
    return _create_token(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        settings=settings,
    )


def create_refresh_token(
    *, user_id: uuid.UUID, organization_id: uuid.UUID, role: UserRole, settings: Settings
) -> str:
    return _create_token(
        user_id=user_id,
        organization_id=organization_id,
        role=role,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        settings=settings,
    )


def decode_token(token: str, settings: Settings) -> dict:
    """
    Decodes and validates a JWT's signature and expiry.

    Raises jwt.PyJWTError subclasses (ExpiredSignatureError,
    InvalidSignatureError, DecodeError, ...) on any failure — callers
    translate those into HTTP 401s; this module stays framework-agnostic.
    """
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
