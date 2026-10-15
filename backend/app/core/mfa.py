"""TOTP two-factor primitives.

Thin wrappers over ``pyotp`` plus at-rest encryption of the shared secret.

The shared secret is encrypted with AES-256-GCM under a key derived (HKDF) from
``CREDENTIALS_ENC_KEY`` when set, falling back to ``SECRET_KEY`` in dev/test so
the feature works locally without a dedicated key. Production validation
requires a strong ``SECRET_KEY`` (and, with credentials configured, a strong
``CREDENTIALS_ENC_KEY``), so the fallback is never weak in production.
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Final

import pyotp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_NONCE_SIZE: Final = 12
_HKDF_INFO: Final = b"agencyos-mfa-secret-v1"
_HKDF_SALT: Final = b"agencyos-mfa-salt"

_RECOVERY_CODE_COUNT: Final = 10
_RECOVERY_ALPHABET: Final = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


def _key() -> bytes:
    material = (settings.CREDENTIALS_ENC_KEY or settings.SECRET_KEY).encode("utf-8")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    ).derive(material)


def generate_secret() -> str:
    """Generate a fresh base32 TOTP shared secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, *, account_name: str) -> str:
    """Return the ``otpauth://`` URI an authenticator app scans."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name, issuer_name=settings.MFA_ISSUER
    )


def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code (one step of clock drift tolerated)."""
    if not code or not code.strip().isdigit():
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def encrypt_mfa_secret(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_mfa_secret(value: str) -> str:
    blob = base64.b64decode(value, validate=True)
    nonce, ciphertext = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")


def generate_recovery_codes(count: int = _RECOVERY_CODE_COUNT) -> list[str]:
    """Return ``count`` human-readable one-time recovery codes."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes
