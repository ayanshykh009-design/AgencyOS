"""Security primitives: password hashing + JWT handling.

Production-grade building blocks:
- password hashing with Argon2id (via pwdlib),
- JWT signing/validation with issuer + audience claims (via PyJWT).

Consumed by auth services and app/api/deps.py. No business logic here.
"""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.errors import AppError

# Argon2id via pwdlib (passlib is unmaintained — do not reintroduce it).
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password (Argon2id)."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its stored Argon2id hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT for `subject` with iat/exp/iss/aud claims."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now
        + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    payload.update(extra_claims or {})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT (signature, expiry, issuer, audience)."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )


def require_valid_token(token: str) -> dict[str, Any]:
    """Decode a token or raise a standardized 401 AppError."""
    try:
        return decode_access_token(token)
    except InvalidTokenError:
        raise AppError(
            code="auth.invalid_token",
            message="Invalid or expired token",
            status_code=401,
        ) from None


# --- Refresh tokens (opaque, rotated) ---


def generate_refresh_token() -> str:
    """Generate an opaque, high-entropy refresh token (returned once)."""
    return token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 digest stored in refresh_tokens.token_hash."""
    return sha256(token.encode("utf-8")).hexdigest()
