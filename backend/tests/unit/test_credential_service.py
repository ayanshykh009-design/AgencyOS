"""Service-layer unit tests: credentials (CRUD + security constraints)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.enums import CredentialType
from app.schemas.credential import CredentialCreate, CredentialUpdate
from app.services.credential_service import CredentialService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
CREDENTIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000901")


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _service() -> CredentialService:
    service = CredentialService(FakeSession())
    service._repo = MagicMock()
    service._repo.flush = AsyncMock()
    service._repo.refresh = AsyncMock()
    service._repo.add = MagicMock()
    return service


def _create() -> CredentialCreate:
    return CredentialCreate(
        organization_id=ORG_ID,
        name="n8n master",
        credential_type=CredentialType.N8N_API_KEY,
        encrypted_value="enc:abc123",
        value_preview="abc1",
        description="n8n instance key",
    )


async def test_create_rejects_duplicate_name() -> None:
    service = _service()
    service._repo.get_by_name = AsyncMock(return_value=MagicMock())

    with pytest.raises(AppError) as exc_info:
        await service.create(_create(), created_by_user_id=USER_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "credential.name_taken"


async def test_create_builds_credential() -> None:
    service = _service()
    service._repo.get_by_name = AsyncMock(return_value=None)
    created: list[object] = []
    service._repo.add.side_effect = lambda instance: created.append(instance)

    await service.create(_create(), created_by_user_id=USER_ID)

    instance = created[0]
    assert instance.organization_id == ORG_ID
    assert instance.encrypted_value == "enc:abc123"
    assert instance.created_by_user_id == USER_ID


async def test_create_commits_transaction() -> None:
    service = _service()
    service._repo.get_by_name = AsyncMock(return_value=None)
    service._repo.add.side_effect = lambda instance: None

    await service.create(_create(), created_by_user_id=USER_ID)

    assert service._session.commits == 1


async def test_update_never_touches_encrypted_value() -> None:
    service = _service()
    credential = MagicMock()
    credential.encrypted_value = "enc:keep"
    credential.value_preview = "keep"
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    await service.update(
        ORG_ID,
        CREDENTIAL_ID,
        CredentialUpdate(
            name="renamed",
            encrypted_value="enc:evil",
            value_preview="evil",
        ),
    )

    assert credential.name == "renamed"
    assert credential.encrypted_value == "enc:keep"
    assert credential.value_preview == "keep"


async def test_get_or_404_delegates() -> None:
    service = _service()
    credential = MagicMock()
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    result = await service.get_or_404(ORG_ID, CREDENTIAL_ID)

    service._repo.get_or_404.assert_awaited_once_with(ORG_ID, CREDENTIAL_ID)
    assert result is credential


async def test_delete_delegates_scoped() -> None:
    service = _service()
    service._repo.delete = AsyncMock(return_value=True)

    result = await service.delete(ORG_ID, CREDENTIAL_ID)

    assert result is True
    service._repo.delete.assert_awaited_once_with(ORG_ID, CREDENTIAL_ID)


async def test_update_last_used_uses_utcnow() -> None:
    service = _service()
    service._repo.update_last_used = AsyncMock(return_value=True)

    result = await service.update_last_used(CREDENTIAL_ID)

    assert result is True
    service._repo.update_last_used.assert_awaited_once()
    assert service._repo.update_last_used.await_args.args[0] == CREDENTIAL_ID
