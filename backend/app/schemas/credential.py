"""Credential schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CredentialType
from app.schemas.common import Page


class CredentialBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    credential_type: CredentialType
    value_preview: str = Field(min_length=1)
    description: str | None = None
    expires_at: datetime | None = None


class CredentialCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    credential_type: CredentialType
    encrypted_value: str = Field(min_length=1, description="Encrypted secret value")
    value_preview: str = Field(min_length=1, description="Masked preview of the secret")
    description: str | None = None
    expires_at: datetime | None = None


class CredentialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    credential_type: CredentialType | None = None
    encrypted_value: str | None = Field(default=None, min_length=1)
    value_preview: str | None = Field(default=None, min_length=1)
    description: str | None = None
    expires_at: datetime | None = None


class CredentialRead(CredentialBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_user_id: uuid.UUID
    last_used_at: datetime | None = None
    key_version: str
    last_rotated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CredentialListResponse(Page[CredentialRead]):
    pass
