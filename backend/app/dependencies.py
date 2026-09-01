"""
Shared FastAPI dependencies (Milestone 4).

get_current_user is the dependency nearly every future protected route will
rely on, either directly or through Milestone 5's require_role() wrapper.
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import TokenType, decode_token
from app.database import get_db
from app.models.user import User, UserRole

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Decodes the bearer access token, loads the corresponding user from the
    database, and raises 401 for any failure mode: missing/malformed
    header, invalid signature, expired token, a refresh token used where an
    access token is required, or a user that no longer exists / has since
    been deactivated. Loading the user (rather than trusting the JWT
    payload alone) is what catches that last case.
    """
    if credentials is None:
        raise _unauthorized()

    try:
        payload = decode_token(credentials.credentials, settings)
    except jwt.PyJWTError:
        raise _unauthorized()

    if payload.get("type") != TokenType.ACCESS.value:
        raise _unauthorized()

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized()

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()

    return user


def require_role(*roles: UserRole):
    """
    Per-route role gate (Milestone 5), e.g.
    Depends(require_role(UserRole.OWNER, UserRole.DISPATCHER)).

    Resolves get_current_user first, so a missing/invalid/expired token
    still 401s before any role check runs; only 403s once we know who the
    caller is and their role isn't in the allowed set.
    """

    async def _require_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _require_role
