"""Team invitation API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import InviteStatus, UserRole


class TeamInviteCreate(BaseModel):
    """Payload to invite a new team member."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.MEMBER

    @field_validator("email")
    @classmethod
    def email_normalized(cls, v: EmailStr) -> str:
        return str(v).strip().lower()


class TeamInviteRead(BaseModel):
    """A team invitation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    email: str
    full_name: str | None = None
    role: UserRole
    status: InviteStatus
    invited_by_user_id: UUID | None = None
    expires_at: datetime
    accepted_at: datetime | None = None
    accepted_user_id: UUID | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TeamInviteCreateResponse(TeamInviteRead):
    """An invite plus the one-time acceptance URL (returned only on create)."""

    invite_url: str


class TeamInviteLookup(BaseModel):
    """Public invite details for the acceptance screen (no token)."""

    model_config = ConfigDict(from_attributes=True)

    email: str
    full_name: str | None = None
    role: UserRole
    organization_name: str | None = None


class TeamInviteAccept(BaseModel):
    """Payload to accept an invite and create the account."""

    token: str = Field(min_length=16, max_length=256)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
