"""Credential repository (org-scoped CRUD + key-version registry)."""

from __future__ import annotations

import builtins
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import Credential, CredentialKeyVersion
from app.models.enums import CredentialType

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class CredentialRepository:
    """Data access for credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> Credential | None:
        stmt = select(Credential).where(
            Credential.organization_id == organization_id,
            Credential.id == credential_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> Credential:
        from app.core.errors import AppError

        credential = await self.get(organization_id, credential_id)
        if credential is None:
            raise AppError(
                code="credential.not_found",
                message="Credential not found",
                status_code=404,
            )
        return credential

    async def get_by_name(self, organization_id: uuid.UUID, name: str) -> Credential | None:
        stmt = select(Credential).where(
            Credential.organization_id == organization_id,
            Credential.name == name,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        credential_type: CredentialType | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Credential]:
        stmt = select(Credential).where(Credential.organization_id == organization_id)
        if credential_type is not None:
            stmt = stmt.where(Credential.credential_type == credential_type)

        sort_col = getattr(Credential, sort, Credential.created_at)
        if order == "desc":
            sort_col = sort_col.desc()
        stmt = stmt.order_by(sort_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        credential_type: CredentialType | None = None,
    ) -> int:
        stmt = (
            select(func.count(Credential.id))
            .where(Credential.organization_id == organization_id)
            .select_from(Credential)
        )
        if credential_type is not None:
            stmt = stmt.where(Credential.credential_type == credential_type)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, credential: Credential) -> None:
        self._session.add(credential)

    async def delete(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> bool:
        credential = await self.get(organization_id, credential_id)
        if credential is None:
            return False
        await self._session.delete(credential)
        return True

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, credential: Credential) -> None:
        await self._session.refresh(credential)

    async def update_last_used(self, credential_id: uuid.UUID) -> bool:
        """Stamp last_used_at on a credential (called after a successful dispatch)."""
        stmt = (
            update(Credential)
            .where(Credential.id == credential_id)
            .values(last_used_at=datetime.now(UTC))
        )
        result = cast(CursorResult, await self._session.execute(stmt))
        return bool(result.rowcount)

    async def list_stale_key(self, current_version: str, limit: int) -> builtins.list[Credential]:
        """Credentials encrypted under an older key version (rekey candidates).

        Oldest-updated first so a rotation completes rows that stalled earlier.
        """
        stmt = (
            select(Credential)
            .where(Credential.key_version != current_version)
            .order_by(Credential.updated_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_stale_key(self, current_version: str) -> int:
        """Count credentials that still need re-encryption under ``current``."""
        stmt = (
            select(func.count(Credential.id))
            .select_from(Credential)
            .where(Credential.key_version != current_version)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_key_version(self, version: str) -> CredentialKeyVersion | None:
        stmt = select(CredentialKeyVersion).where(CredentialKeyVersion.version == version)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_key_version(self, version: str, fingerprint: str) -> None:
        """Insert (or refresh the fingerprint of) a key-version registry row."""
        row = await self.get_key_version(version)
        if row is None:
            self._session.add(CredentialKeyVersion(version=version, key_fingerprint=fingerprint))
        else:
            row.key_fingerprint = fingerprint

    async def retire_key_version(self, version: str) -> bool:
        """Mark a key version as retired (safe once no rows reference it)."""
        row = await self.get_key_version(version)
        if row is None or row.status == "retired":
            return False
        row.status = "retired"
        row.retired_at = datetime.now(UTC)
        return True
