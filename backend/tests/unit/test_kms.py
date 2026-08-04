"""Tests for the KMS layer: envelope encryption, key versioning, rotation."""
from __future__ import annotations

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core import crypto
from app.core.config import settings
from app.core.kms import get_kms_provider, reset_provider

KEY_1 = "test-master-key-one"
KEY_2 = "test-master-key-two"
KEY_3 = "test-master-key-three"


@pytest.fixture(autouse=True)
def _key_settings(monkeypatch):
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", KEY_1)
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", "")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "1")
    yield
    reset_provider()


def test_envelope_roundtrip_current_key() -> None:
    secret = "sk-prod-abc123"
    envelope = crypto.encrypt_secret(secret)
    assert envelope.startswith("v1:")
    assert envelope != secret
    assert crypto.decrypt_secret(envelope) == secret
    assert crypto.decrypt_secret(envelope, key_version="1") == secret


def test_envelopes_are_nonce_randomized() -> None:
    assert crypto.encrypt_secret("same-secret") != crypto.encrypt_secret("same-secret")


def test_decrypt_legacy_plaintext_passthrough() -> None:
    """Pre-versioning rows stored the secret verbatim — never touched."""
    assert crypto.decrypt_secret("plaintext-secret") == "plaintext-secret"
    assert crypto.decrypt_secret("") == ""


def test_decrypt_legacy_base64_envelope() -> None:
    """The pre-versioning format (base64(nonce||ct), no prefix) still decrypts."""
    key = crypto._derive_key(KEY_1)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, b"legacy-secret", None)
    legacy = base64.b64encode(nonce + ct).decode("ascii")
    assert crypto.decrypt_secret(legacy) == "legacy-secret"


def test_dual_read_during_master_key_rotation(monkeypatch) -> None:
    envelope_v1 = crypto.encrypt_secret("old-secret")
    assert envelope_v1.startswith("v1:")

    # Rotate: new key becomes current, old key moves to PREVIOUS.
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", KEY_2)
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", KEY_1)
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "2")

    # v1 rows stay readable through the previous key (dual-read).
    assert crypto.decrypt_secret(envelope_v1, key_version="1") == "old-secret"
    # New rows encrypt under v2.
    envelope_v2 = crypto.encrypt_secret("new-secret")
    assert envelope_v2.startswith("v2:")
    assert crypto.decrypt_secret(envelope_v2) == "new-secret"


def test_legacy_plaintext_readable_after_rotation(monkeypatch) -> None:
    legacy = "raw-plaintext-secret"
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", KEY_2)
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", KEY_1)
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "2")
    # Legacy plaintext is returned as-is (no key material involved).
    assert crypto.decrypt_secret(legacy, key_version="0") == legacy


def test_unsupported_key_version_raises(monkeypatch) -> None:
    envelope = crypto.encrypt_secret("secret")
    # Current becomes 9 with no material for v1 → must fail loudly.
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", KEY_3)
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "9")
    with pytest.raises(ValueError):
        crypto.decrypt_secret(envelope)


def test_versioned_corruption_rejected() -> None:
    envelope = crypto.encrypt_secret("secret")
    mid = len(envelope) // 2
    corrupted = envelope[:mid] + ("A" if envelope[mid] != "A" else "B") + envelope[mid + 1:]
    with pytest.raises(InvalidTag):
        crypto.decrypt_secret(corrupted)


def test_key_fingerprint_stable_and_key_sensitive(monkeypatch) -> None:
    before = crypto.key_fingerprint("1")
    assert before == crypto.key_fingerprint("1")
    assert len(before) == 64
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", KEY_2)
    assert crypto.key_fingerprint("1") != before


def test_previous_key_version_accessor(monkeypatch) -> None:
    assert crypto.previous_key_version() is None
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", KEY_1)
    assert crypto.previous_key_version() == "0"


def test_env_provider_delegates() -> None:
    provider = get_kms_provider()
    assert provider.current_key_version() == "1"
    assert provider.previous_key_version() is None
    envelope = provider.encrypt_secret("provider-secret")
    assert envelope.startswith("v1:")
    assert provider.decrypt_secret(envelope) == "provider-secret"
    assert len(provider.key_fingerprint()) == 64
