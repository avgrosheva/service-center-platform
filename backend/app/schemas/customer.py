"""Pydantic v2 schemas for Customer (Milestone 6)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# "Basic — don't over-engineer international formats" per the roadmap: just
# require enough digits to plausibly be a phone number, not a full format
# grammar. The CIS-focused market this targets uses varied punctuation
# (spaces, dashes, parens, a leading +), so counting digits rather than
# matching a fixed pattern avoids rejecting valid numbers over formatting.
_PHONE_MIN_DIGITS = 7


def _validate_phone_digits(value: str) -> str:
    if sum(ch.isdigit() for ch in value) < _PHONE_MIN_DIGITS:
        raise ValueError(f"phone must contain at least {_PHONE_MIN_DIGITS} digits")
    return value


class CustomerBase(BaseModel):
    full_name: str = Field(min_length=1)
    phone: str
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone_has_enough_digits(cls, value: str) -> str:
        return _validate_phone_digits(value)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1)
    phone: str | None = None
    notes: str | None = None
    is_active: bool | None = None

    @field_validator("phone")
    @classmethod
    def _phone_has_enough_digits(cls, value: str | None) -> str | None:
        return value if value is None else _validate_phone_digits(value)


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
