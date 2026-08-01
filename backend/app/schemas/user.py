"""User API schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class UserBase(BaseModel):
    """Fields a client can set on a user."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.MEMBER

    @field_validator("email")
    @classmethod
    def email_normalized(cls, v: EmailStr) -> str:
        return str(v).strip().lower()


class UserCreate(UserBase):
    """Payload to create a user."""

    organization_id: UUID


class UserUpdate(BaseModel):
    """Partial update of a user (all fields optional)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserRead(UserBase):
    """Full user representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
