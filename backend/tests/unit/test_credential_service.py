"""Service-layer unit tests: credentials (CRUD + security constraints)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.core.kms import get_kms_provider, reset_provider
from app.models.enums import CredentialType
from app.schemas.credential import CredentialCreate, CredentialUpdate
from app.services.credential_service import CredentialService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
CREDENTIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000901")


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "unit-test-key")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "1")
    yield
    reset_provider()


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
    assert instance.encrypted_value != "enc:abc123"
    assert instance.encrypted_value.startswith("v1:")
    assert instance.key_version == "1"
    assert instance.created_by_user_id == USER_ID


async def test_create_encrypts_value_at_rest() -> None:
    service = _service()
    service._repo.get_by_name = AsyncMock(return_value=None)
    created: list[object] = []
    service._repo.add.side_effect = lambda instance: created.append(instance)

    await service.create(_create(), created_by_user_id=USER_ID)

    stored = created[0].encrypted_value
    provider = get_kms_provider()
    assert provider.decrypt_secret(stored, key_version="1") == "enc:abc123"


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


async def test_get_secret_returns_decrypted_value() -> None:
    service = _service()
    provider = get_kms_provider()
    credential = MagicMock()
    credential.encrypted_value = provider.encrypt_secret("super-secret")
    credential.key_version = "1"
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    secret = await service.get_secret(ORG_ID, CREDENTIAL_ID)

    assert secret == "super-secret"
    service._repo.get_or_404.assert_awaited_once_with(ORG_ID, CREDENTIAL_ID)


async def test_get_secret_upgrades_legacy_plaintext() -> None:
    service = _service()
    credential = MagicMock()
    credential.encrypted_value = "raw-plaintext-secret"
    credential.key_version = "0"
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    assert await service.get_secret(ORG_ID, CREDENTIAL_ID) == "raw-plaintext-secret"


async def test_rotate_reencrypts_with_current_key() -> None:
    service = _service()
    credential = MagicMock()
    credential.encrypted_value = "legacy-plaintext"
    credential.key_version = "0"
    credential.last_rotated_at = None
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    result = await service.rotate(ORG_ID, CREDENTIAL_ID)

    provider = get_kms_provider()
    assert result.encrypted_value.startswith("v1:")
    assert provider.decrypt_secret(result.encrypted_value, key_version="1") == "legacy-plaintext"
    assert result.key_version == "1"
    assert result.last_rotated_at is not None
    assert service._session.commits == 1


async def test_rotate_bumps_version_during_rotation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "old-key")
    service = _service()
    provider = get_kms_provider()
    credential = MagicMock()
    credential.encrypted_value = provider.encrypt_secret("secret")  # v1
    credential.key_version = "1"
    credential.last_rotated_at = None
    service._repo.get_or_404 = AsyncMock(return_value=credential)

    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "new-key")
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", "old-key")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "2")

    result = await service.rotate(ORG_ID, CREDENTIAL_ID)

    assert result.key_version == "2"
    assert result.encrypted_value.startswith("v2:")
    assert provider.decrypt_secret(result.encrypted_value) == "secret"


async def test_list_stale_key_delegates() -> None:
    service = _service()
    service._repo.list_stale_key = AsyncMock(return_value=[])

    result = await service.list_stale_key("2", 25)

    assert result == []
    service._repo.list_stale_key.assert_awaited_once_with("2", 25)


async def test_count_stale_key_delegates() -> None:
    service = _service()
    service._repo.count_stale_key = AsyncMock(return_value=3)

    assert await service.count_stale_key("2") == 3


async def test_upsert_key_version_delegates() -> None:
    service = _service()
    service._repo.upsert_key_version = AsyncMock()

    await service.upsert_key_version("2", "abcd" * 16)

    service._repo.upsert_key_version.assert_awaited_once_with("2", "abcd" * 16)


async def test_retire_key_version_delegates() -> None:
    service = _service()
    service._repo.retire_key_version = AsyncMock(return_value=True)

    assert await service.retire_key_version("1") is True
    service._repo.retire_key_version.assert_awaited_once_with("1")
