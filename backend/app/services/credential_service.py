"""Credential service: CRUD + security constraints + key rotation."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.kms import get_kms_provider
from app.models.credential import Credential
from app.models.enums import CredentialType
from app.repositories.credential import CredentialRepository
from app.schemas.credential import CredentialCreate, CredentialUpdate
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.security.credentials")


class CredentialService:
    """Owns credential business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CredentialRepository(session)

    async def create(
        self,
        data: CredentialCreate,
        *,
        created_by_user_id: uuid.UUID,
    ) -> Credential:
        if data.organization_id is None:
            raise AppError(
                code="credential.organization_required",
                message="organization_id is required",
                status_code=400,
            )

        existing = await self._repo.get_by_name(data.organization_id, data.name)
        if existing is not None:
            raise AppError(
                code="credential.name_taken",
                message="A credential with this name already exists",
                status_code=409,
            )

        provider = get_kms_provider()
        credential = Credential(
            organization_id=data.organization_id,
            name=data.name,
            credential_type=data.credential_type,
            encrypted_value=provider.encrypt_secret(data.encrypted_value),
            value_preview=data.value_preview,
            description=data.description,
            expires_at=data.expires_at,
            created_by_user_id=created_by_user_id,
            key_version=provider.current_key_version(),
        )
        self._repo.add(credential)
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="credential.name_taken",
                message="A credential with this name already exists",
                status_code=409,
            ) from exc
        await commit_with_retry(self._session)
        return credential

    async def update(
        self,
        organization_id: uuid.UUID,
        credential_id: uuid.UUID,
        data: CredentialUpdate,
    ) -> Credential:
        """Update credential metadata. Never touches the stored secret."""
        credential = await self._repo.get_or_404(organization_id, credential_id)

        if data.name is not None:
            credential.name = data.name
        if data.credential_type is not None:
            credential.credential_type = data.credential_type
        if data.description is not None:
            credential.description = data.description
        if data.expires_at is not None:
            credential.expires_at = data.expires_at

        await commit_with_retry(self._session)
        return credential

    async def delete(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> bool:
        return await self._repo.delete(organization_id, credential_id)

    async def get_or_404(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> Credential:
        return await self._repo.get_or_404(organization_id, credential_id)

    async def get_secret(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> str:
        """Decrypt and return the stored secret.

        Adaptors only — never exposed via any endpoint. Raises
        ``credential.not_found`` if the credential does not exist and
        propagates decryption failures (corruption is surfaced, not masked).
        """
        credential = await self._repo.get_or_404(organization_id, credential_id)
        return get_kms_provider().decrypt_secret(
            credential.encrypted_value, key_version=credential.key_version
        )

    async def rotate(self, organization_id: uuid.UUID, credential_id: uuid.UUID) -> Credential:
        """Re-encrypt the secret with the current key and bump its version.

        Backward compatible: pre-versioning plaintext/legacy values are
        decrypted transparently and upgraded to encrypted-at-rest on rotation.
        """
        credential = await self._repo.get_or_404(organization_id, credential_id)
        provider = get_kms_provider()
        plaintext = provider.decrypt_secret(
            credential.encrypted_value, key_version=credential.key_version
        )
        credential.encrypted_value = provider.encrypt_secret(plaintext)
        credential.key_version = provider.current_key_version()
        credential.last_rotated_at = utcnow()
        await commit_with_retry(self._session)
        logger.info(
            "credential %s rotated to key version %s",
            credential_id,
            credential.key_version,
        )
        return credential

    async def list_stale_key(self, current_version: str, limit: int) -> list[Credential]:
        return await self._repo.list_stale_key(current_version, limit)

    async def count_stale_key(self, current_version: str) -> int:
        return await self._repo.count_stale_key(current_version)

    async def upsert_key_version(self, version: str, fingerprint: str) -> None:
        await self._repo.upsert_key_version(version, fingerprint)

    async def retire_key_version(self, version: str) -> bool:
        return await self._repo.retire_key_version(version)

    async def update_last_used(self, credential_id: uuid.UUID) -> bool:
        return await self._repo.update_last_used(credential_id)

    async def list_credentials(
        self,
        organization_id: uuid.UUID,
        *,
        credential_type: CredentialType | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Credential]:
        return await self._repo.list(
            organization_id,
            credential_type=credential_type,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count_credentials(
        self,
        organization_id: uuid.UUID,
        *,
        credential_type: CredentialType | None = None,
    ) -> int:
        return await self._repo.count(
            organization_id,
            credential_type=credential_type,
        )
