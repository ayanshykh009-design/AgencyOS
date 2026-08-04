"""Credential model — encrypted credential storage for integrations."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CredentialType

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Credential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An encrypted credential for external integrations."""

    __tablename__ = "credentials"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="chk_credentials_name_not_blank"),
        CheckConstraint("length(value_preview) > 0", name="chk_credentials_preview_not_blank"),
        UniqueConstraint("organization_id", "name", name="uq_credentials_org_name"),
        Index("idx_credentials_org_type", "organization_id", "credential_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    credential_type: Mapped[CredentialType] = mapped_column(
        Enum(CredentialType, name="credential_type", native_enum=True, validate_strings=True),
        nullable=False,
    )
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    value_preview: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column()
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column()

    created_by: Mapped[User] = relationship()
    organization: Mapped[Organization] = relationship(back_populates="credentials")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Credential id={self.id} name={self.name!r} type={self.credential_type}>"