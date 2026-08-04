"""Encryption utilities for credential storage (Fernet/AES-256-GCM).

The encryption key is derived from ``CREDENTIALS_ENC_KEY`` via HKDF-SHA256.
A per-credential nonce (12 bytes) is prepended to the ciphertext.
"""
from __future__ import annotations

import base64
import os
from typing import Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_KEY_SIZE: Final = 32  # AES-256
_NONCE_SIZE: Final = 12  # 96-bit nonce for AES-GCM
_HKDF_INFO: Final = b"agencyos-credential-encryption"


def _derive_key(raw: str) -> bytes:
    """Derive a 32-byte key from the raw config string via HKDF-SHA256."""
    salt = b"agencyos-credential-salt"  # static salt; key derivation is deterministic
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=salt,
        info=_HKDF_INFO,
    )
    return hkdf.derive(raw.encode("utf-8"))


_ENCRYPTION_KEY: bytes | None = None


def _get_key() -> bytes:
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        raw = settings.CREDENTIALS_ENC_KEY
        if not raw:
            raise RuntimeError("CREDENTIALS_ENC_KEY is not configured")
        _ENCRYPTION_KEY = _derive_key(raw)
    return _ENCRYPTION_KEY


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string. Returns base64(nonce || ciphertext || tag)."""
    key = _get_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # nonce (12) || ciphertext+tag (variable)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(ciphertext_b64: str) -> str:
    """Decrypt a secret string produced by ``encrypt_secret``."""
    key = _get_key()
    data = base64.b64decode(ciphertext_b64)
    if len(data) < _NONCE_SIZE + 16:  # nonce + min tag
        raise ValueError("Invalid ciphertext length")
    nonce = data[:_NONCE_SIZE]
    ct = data[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def mask_secret(value: str, visible: int = 4) -> str:
    """Return a masked preview of a secret (last N chars visible)."""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]