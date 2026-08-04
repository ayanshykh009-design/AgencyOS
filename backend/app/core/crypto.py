"""Encryption utilities for credential storage (envelope encryption).

Phase 5B introduces key-versioned envelope encryption:

- ``encrypt_secret`` wraps plaintext as ``v<version>:<base64(nonce || ct)>``
  using the *current* master key (derived from ``CREDENTIALS_ENC_KEY`` via
  HKDF-SHA256).
- ``decrypt_secret`` reads the version prefix and authenticates with the
  matching key (current, or ``CREDENTIALS_ENC_KEY_PREVIOUS`` during rotation).
- Pre-versioning rows — stored verbatim (never encrypted) or as the legacy
  ``base64(nonce || ct)`` envelope — are detected and handled transparently;
  the rekey worker upgrades them to encrypted-at-rest.
- No key material is ever stored; ``key_fingerprint`` exposes a stable
  identifier (SHA-256 of the derived key) for the credential_key_versions
  registry.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_KEY_SIZE: Final = 32  # AES-256
_NONCE_SIZE: Final = 12  # 96-bit nonce for AES-GCM
_HKDF_INFO: Final = b"agencyos-credential-encryption"
_HKDF_SALT: Final = b"agencyos-credential-salt"
_MIN_BLOB_LENGTH: Final = _NONCE_SIZE + 16  # nonce + GCM tag
_LEGACY_VERSION: Final = "0"  # rows stored before key versioning existed
_VERSION_PREFIX_RE: Final = re.compile(r"^v([0-9]+):")


def _derive_key(raw: str) -> bytes:
    """Derive a 32-byte key from the raw config string via HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(raw.encode("utf-8"))


def _previous_version(current: str) -> str:
    """Return the version label one step below ``current`` (min ``0``)."""
    try:
        return str(max(int(current) - 1, 0))
    except ValueError:
        return _LEGACY_VERSION


def _key_material(version: str) -> str | None:
    """Return the configured raw key material for a version (or None)."""
    current = settings.CREDENTIAL_KEY_VERSION
    if version == current:
        return settings.CREDENTIALS_ENC_KEY or None
    if version == _previous_version(current) and settings.CREDENTIALS_ENC_KEY_PREVIOUS:
        return settings.CREDENTIALS_ENC_KEY_PREVIOUS
    return None


_key_cache: dict[tuple[str, str], bytes] = {}


def _key_for(version: str) -> bytes:
    """Return the 32-byte AES key for a version label (raises if unknown)."""
    raw = _key_material(version)
    if raw is None:
        raise ValueError(f"Unsupported credential key version: {version}")
    cache_key = (version, raw)
    cached = _key_cache.get(cache_key)
    if cached is None:
        cached = _derive_key(raw)
        _key_cache[cache_key] = cached
    return cached


def current_key_version() -> str:
    """Version label of the active (encryption) key."""
    return settings.CREDENTIAL_KEY_VERSION


def previous_key_version() -> str | None:
    """Version label of the dual-read key during rotation (or None)."""
    if not settings.CREDENTIALS_ENC_KEY_PREVIOUS:
        return None
    return _previous_version(settings.CREDENTIAL_KEY_VERSION)


def key_fingerprint(version: str | None = None) -> str:
    """Stable identifier for a key version (SHA-256 of the derived key)."""
    key = _key_for(version or settings.CREDENTIAL_KEY_VERSION)
    return hashlib.sha256(key).hexdigest()


def _get_key() -> bytes:
    """Return the current AES key (legacy internal accessor)."""
    return _key_for(settings.CREDENTIAL_KEY_VERSION)


def _parse_envelope(value: str) -> tuple[str, bytes] | None:
    """Split ``v<N>:<base64(nonce||ct)>`` into (version, blob); else None."""
    match = _VERSION_PREFIX_RE.match(value)
    if not match:
        return None
    try:
        blob = base64.b64decode(value[match.end():], validate=True)
    except (ValueError, TypeError):
        return None
    if len(blob) < _MIN_BLOB_LENGTH:
        return None
    return match.group(1), blob


def _legacy_candidates(db_version: str | None) -> list[str]:
    """Ordered key versions to try for a legacy (non-prefixed) blob."""
    current = settings.CREDENTIAL_KEY_VERSION
    candidates = [db_version, current, _previous_version(current)]
    known: list[str] = []
    for version in candidates:
        if version and version not in known and _key_material(version) is not None:
            known.append(version)
    return known


def encrypt_secret(plaintext: str, *, key_version: str | None = None) -> str:
    """Encrypt a secret under the current key into a versioned envelope.

    Returns ``v<version>:<base64(nonce || ciphertext || tag)>``.
    """
    version = key_version or settings.CREDENTIAL_KEY_VERSION
    key = _key_for(version)
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = base64.b64encode(nonce + ciphertext).decode("ascii")
    return f"v{version}:{blob}"


def decrypt_secret(ciphertext: str, *, key_version: str | None = None) -> str:
    """Decrypt a stored credential value.

    Handles versioned envelopes, the legacy ``base64(nonce||ct)`` format, and
    pre-versioning plaintext values (returned unchanged). Versioned blobs that
    fail authentication raise — corruption is never silently accepted.
    """
    parsed = _parse_envelope(ciphertext)
    if parsed is not None:
        version, blob = parsed
        key = _key_for(version)
        nonce, ct = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
        plaintext = AESGCM(key).decrypt(nonce, ct, None)
        return plaintext.decode("utf-8")

    try:
        blob = base64.b64decode(ciphertext, validate=True)
    except (ValueError, TypeError):
        return ciphertext
    if len(blob) < _MIN_BLOB_LENGTH:
        return ciphertext
    for version in _legacy_candidates(key_version):
        nonce, ct = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
        try:
            plaintext = AESGCM(_key_for(version)).decrypt(nonce, ct, None)
        except Exception:
            continue
        return plaintext.decode("utf-8")
    return ciphertext


def mask_secret(value: str, visible: int = 4) -> str:
    """Return a masked preview of a secret (last N chars visible)."""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
