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
        Enum(
            CredentialType,
            name="credential_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
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
    # Envelope-encryption key version. "0" marks rows stored before key
    # versioning existed (plaintext or legacy envelope) — the rekey worker
    # upgrades them to the current version.
    key_version: Mapped[str] = mapped_column(Text, nullable=False, default="0", server_default="0")
    last_rotated_at: Mapped[datetime | None] = mapped_column()

    created_by: Mapped[User] = relationship()
    organization: Mapped[Organization] = relationship(back_populates="credentials")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Credential id={self.id} name={self.name!r} type={self.credential_type}>"


class CredentialKeyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registry/audit of credential encryption key versions.

    The rekey worker upserts the current (and, during rotation, previous) key
    version with a stable fingerprint, and retires the previous version once
    no credential rows reference it anymore.
    """

    __tablename__ = "credential_key_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="chk_credential_key_versions_status",
        ),
    )

    version: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    retired_at: Mapped[datetime | None] = mapped_column()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CredentialKeyVersion version={self.version!r} status={self.status!r}>"
