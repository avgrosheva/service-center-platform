"""Pydantic v2 schemas for User (Milestone 3)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole

# Same rule as CustomerBase's phone (see schemas/customer.py) — count
# digits rather than match a fixed format, for the same varied-punctuation
# reason. Duplicated rather than imported: the two phone fields belong to
# unrelated resources (a user's own contact info vs. a customer's), and
# staying independent means one can change its rule without the other
# silently following.
_PHONE_MIN_DIGITS = 7


def _validate_phone_digits(value: str) -> str:
    if sum(ch.isdigit() for ch in value) < _PHONE_MIN_DIGITS:
        raise ValueError(f"phone must contain at least {_PHONE_MIN_DIGITS} digits")
    return value


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    """
    PATCH /users/{id} body (Milestone 5) — role and/or active status, plus
    `password` (owner resetting a teammate's forgotten password — the one
    account-recovery path that doesn't require the account holder to
    already be signed in, unlike everything under /auth/me). All optional
    so a caller can change just one without resending the others.
    """

    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MeUpdate(BaseModel):
    """
    PATCH /auth/me body — a user editing their own profile. Every field is
    optional so a caller can change just one; `phone` additionally accepts
    `""` to mean "clear it" (it's the one nullable field here), matching
    CustomerUpdate's own phone convention.
    """

    full_name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone_valid_or_empty(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        return _validate_phone_digits(value)


class MeRead(UserRead):
    # Not a persisted column — see avatar_s3_key's docstring on
    # models/user.py. `None` when the user has never uploaded one.
    avatar_url: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


AvatarContentType = Literal["image/jpeg", "image/png", "image/webp", "image/heic"]


class AvatarUploadURLRequest(BaseModel):
    content_type: AvatarContentType


class AvatarUploadURLResponse(BaseModel):
    upload_url: str
    s3_key: str


class AvatarConfirmRequest(BaseModel):
    s3_key: str