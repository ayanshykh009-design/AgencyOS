"""Pluggable key-management providers for credential encryption.

Phase 5B introduces envelope encryption with key versioning. The default
provider (``EnvKeyProvider``) derives keys from the ``CREDENTIALS_ENC_KEY`` /
``CREDENTIALS_ENC_KEY_PREVIOUS`` settings via ``app.core.crypto``. A future
cloud KMS (AWS/Azure/GCP) can be added by implementing ``KmsProvider`` and
switching ``get_kms_provider`` — callers depend only on this interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.core import crypto

logger = logging.getLogger("agencyos.security.kms")


class KmsProvider(ABC):
    """Encrypt/decrypt secrets with explicit key-version management."""

    @abstractmethod
    def current_key_version(self) -> str:
        """Version label of the active (encryption) key."""

    @abstractmethod
    def previous_key_version(self) -> str | None:
        """Version label of the dual-read key during rotation (or None)."""

    @abstractmethod
    def encrypt_secret(self, plaintext: str) -> str:
        """Encrypt under the current key; returns a versioned envelope."""

    @abstractmethod
    def decrypt_secret(self, ciphertext: str, *, key_version: str | None = None) -> str:
        """Decrypt a stored envelope or a pre-versioning plaintext value."""

    @abstractmethod
    def key_fingerprint(self, version: str | None = None) -> str:
        """Stable identifier for a key version (never the key material)."""


class EnvKeyProvider(KmsProvider):
    """KMS provider backed by environment-configured keys (HKDF-derived)."""

    def current_key_version(self) -> str:
        return crypto.current_key_version()

    def previous_key_version(self) -> str | None:
        return crypto.previous_key_version()

    def encrypt_secret(self, plaintext: str) -> str:
        return crypto.encrypt_secret(plaintext)

    def decrypt_secret(self, ciphertext: str, *, key_version: str | None = None) -> str:
        return crypto.decrypt_secret(ciphertext, key_version=key_version)

    def key_fingerprint(self, version: str | None = None) -> str:
        return crypto.key_fingerprint(version)


_provider: KmsProvider | None = None


def get_kms_provider() -> KmsProvider:
    """Return the configured (cached) KMS provider."""
    global _provider
    if _provider is None:
        _provider = EnvKeyProvider()
    return _provider


def reset_provider() -> None:
    """Drop the cached provider instance (test helper)."""
    global _provider
    _provider = None
