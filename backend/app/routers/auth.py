"""
Auth endpoints (Milestone 4): register, login, refresh, me.

Milestone 19 adds a rate-limit dependency on /login — see
core/rate_limit.py for why login specifically, and why it's IP-keyed and
in-memory rather than per-account or Redis-backed.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.rate_limit import enforce_login_rate_limit
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import (
    AvatarConfirmRequest,
    AvatarUploadURLRequest,
    AvatarUploadURLResponse,
    MeRead,
    MeUpdate,
    PasswordChangeRequest,
)
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    return await auth_service.register(db, data, settings)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(enforce_login_rate_limit)])
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    try:
        return await auth_service.login(db, data.email, data.password, settings)
    except (auth_service.InvalidCredentialsError, auth_service.InactiveUserError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    try:
        access_token = await auth_service.refresh_access_token(db, data.refresh_token, settings)
    except auth_service.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AccessTokenResponse(access_token=access_token)


@router.get("/me", response_model=MeRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return user_service.attach_avatar_url(current_user)


@router.patch("/me", response_model=MeRead)
async def update_me(
    data: MeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        return await user_service.update_me(db, current_user, data)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in this organization",
        ) from exc


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    data: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        await user_service.change_password(db, current_user, data.current_password, data.new_password)
    except user_service.InvalidCurrentPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/me/avatar/upload-url", response_model=AvatarUploadURLResponse)
async def get_my_avatar_upload_url(
    data: AvatarUploadURLRequest,
    current_user: User = Depends(get_current_user),
) -> AvatarUploadURLResponse:
    upload_url, s3_key = user_service.generate_avatar_upload_url(current_user, data.content_type)
    return AvatarUploadURLResponse(upload_url=upload_url, s3_key=s3_key)


@router.post("/me/avatar", response_model=MeRead)
async def confirm_my_avatar(
    data: AvatarConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        return await user_service.set_avatar(db, current_user, data.s3_key)
    except user_service.InvalidAvatarKeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/me/avatar", response_model=MeRead)
async def delete_my_avatar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    return await user_service.clear_avatar(db, current_user)
