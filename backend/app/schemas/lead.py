"""Lead API schemas.

Normalized dedup keys (``email_normalized``, ``phone_normalized``,
``website_domain``) are read-only: they are computed by PostgreSQL and never
accepted from clients.
"""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import LeadStatus

_SCORE_MAX = 100


def _normalize_phone(raw: str | None) -> str | None:
    """Strip non-digits (mirrors DB normalizer); None when empty."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits or None


def _normalize_domain(url: str | None) -> str | None:
    """Extract a lowercased domain without scheme/www/path/trailing dots."""
    if not url:
        return None
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url.strip())
    host = re.sub(r"/.*$", "", host)
    host = re.sub(r"^www\.", "", host, flags=re.IGNORECASE)
    return host.strip(".").lower() or None


class LeadBase(BaseModel):
    """Fields a client can set on a lead."""

    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    notes: str | None = None
    status: LeadStatus = LeadStatus.NEW
    score: int = Field(default=0, ge=0, le=_SCORE_MAX)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: EmailStr | None) -> str | None:
        if v is None:
            return None
        return str(v).strip().lower()

    @field_validator("phone", "whatsapp")
    @classmethod
    def phone_digits(cls, v: str | None) -> str | None:
        return _normalize_phone(v)

    @field_validator("website")
    @classmethod
    def website_trimmed(cls, v: str | None) -> str | None:
        return v.strip() if v else None

    @model_validator(mode="after")
    def at_least_one_contact(self) -> LeadBase:
        if not any((self.email, self.phone, self.whatsapp, self.website)):
            raise ValueError(
                "at least one contact channel (email/phone/whatsapp/website) is required"
            )
        return self


class LeadCreate(LeadBase):
    """Payload to create a lead."""

    organization_id: UUID
    lead_source_id: UUID | None = None
    owner_user_id: UUID | None = None


class LeadUpdate(BaseModel):
    """Partial update of a lead (all fields optional)."""

    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    notes: str | None = None
    status: LeadStatus | None = None
    score: int | None = Field(default=None, ge=0, le=_SCORE_MAX)
    lead_source_id: UUID | None = None
    owner_user_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: EmailStr | None) -> str | None:
        if v is None:
            return None
        return str(v).strip().lower()


class LeadRead(LeadBase):
    """Full lead representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    lead_source_id: UUID | None = None
    owner_user_id: UUID | None = None
    email_normalized: str | None = None
    phone_normalized: str | None = None
    website_domain: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
