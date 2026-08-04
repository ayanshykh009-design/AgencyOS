"""Unit tests for the credential rekey worker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import crypto
from app.core.config import settings
from app.core.kms import get_kms_provider, reset_provider
from app.core.metrics import reset as reset_metrics
from app.workers.credential_worker import CredentialWorker


class _FakeSession:
    async def commit(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _Cred:
    def __init__(self, cid: str, value: str, version: str) -> None:
        self.id = cid
        self.encrypted_value = value
        self.key_version = version
        self.last_rotated_at = None


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "CREDENTIAL_REKEY_ENABLED", True)
    monkeypatch.setattr(settings, "CREDENTIAL_REKEY_BATCH", 100)
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "worker-test-key")
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", "")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "1")
    yield
    reset_metrics()
    reset_provider()


def _patch_service(monkeypatch, service: AsyncMock, session: _FakeSession) -> AsyncMock:
    monkeypatch.setattr(
        "app.workers.credential_worker.async_session_factory",
        MagicMock(return_value=session),
    )
    monkeypatch.setattr(
        "app.workers.credential_worker.CredentialService",
        lambda _session: service,
    )
    return service


async def test_disabled_returns_zeros(monkeypatch) -> None:
    monkeypatch.setattr(settings, "CREDENTIAL_REKEY_ENABLED", False)

    stats = await CredentialWorker.rekey_tick()

    assert stats == {"rekeyed": 0, "stale": 0}


async def test_rekey_upgrades_legacy_plaintext(monkeypatch) -> None:
    service = AsyncMock()
    rows = [_Cred("cred-1", "plain-secret-a", "0")]
    service.list_stale_key = AsyncMock(return_value=rows)
    service.count_stale_key = AsyncMock(return_value=0)
    service.retire_key_version = AsyncMock(return_value=True)
    _patch_service(monkeypatch, service, _FakeSession())

    stats = await CredentialWorker.rekey_tick()

    assert stats == {"rekeyed": 1, "stale": 0}
    provider = get_kms_provider()
    assert rows[0].key_version == "1"
    assert rows[0].encrypted_value.startswith("v1:")
    assert provider.decrypt_secret(rows[0].encrypted_value) == "plain-secret-a"
    assert rows[0].last_rotated_at is not None
    service.upsert_key_version.assert_awaited()
    # No previous key exists (fresh versioning) → nothing to retire.
    service.retire_key_version.assert_not_awaited()


async def test_rekey_keeps_previous_active_while_stale_remain(monkeypatch) -> None:
    service = AsyncMock()
    service.list_stale_key = AsyncMock(return_value=[])
    service.count_stale_key = AsyncMock(return_value=5)
    _patch_service(monkeypatch, service, _FakeSession())

    stats = await CredentialWorker.rekey_tick()

    assert stats == {"rekeyed": 0, "stale": 5}
    service.retire_key_version.assert_not_awaited()


async def test_rekey_skips_row_that_fails_decrypt(monkeypatch) -> None:
    # A real envelope whose ciphertext is corrupted: versioned path must raise
    # (InvalidTag) so the row is skipped, never re-encrypted into garbage.
    good = crypto.encrypt_secret("secret")
    mid = len(good) // 2
    bad_value = good[:mid] + ("A" if good[mid] != "A" else "B") + good[mid + 1:]

    service = AsyncMock()
    corrupt = _Cred("cred-bad", bad_value, "1")
    service.list_stale_key = AsyncMock(return_value=[corrupt])
    service.count_stale_key = AsyncMock(return_value=1)
    _patch_service(monkeypatch, service, _FakeSession())

    stats = await CredentialWorker.rekey_tick()

    assert stats == {"rekeyed": 0, "stale": 1}
    # The failed row must be left untouched (never re-encrypted into garbage).
    assert corrupt.encrypted_value == bad_value
    assert corrupt.key_version == "1"


async def test_rekey_during_master_key_rotation(monkeypatch) -> None:
    # Encrypt a row under v1 first.
    v1_value = crypto.encrypt_secret("rotated-secret")
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "new-master-key")
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", "worker-test-key")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "2")

    service = AsyncMock()
    rows = [_Cred("cred-2", v1_value, "1")]
    service.list_stale_key = AsyncMock(return_value=rows)
    service.count_stale_key = AsyncMock(return_value=0)
    service.retire_key_version = AsyncMock(return_value=True)
    _patch_service(monkeypatch, service, _FakeSession())

    stats = await CredentialWorker.rekey_tick()

    assert stats == {"rekeyed": 1, "stale": 0}
    assert rows[0].key_version == "2"
    assert rows[0].encrypted_value.startswith("v2:")
    provider = get_kms_provider()
    assert provider.decrypt_secret(rows[0].encrypted_value) == "rotated-secret"
