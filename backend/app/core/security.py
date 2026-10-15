"""Security primitives: password hashing + JWT handling.

Production-grade building blocks:
- password hashing with Argon2id (via pwdlib),
- JWT signing/validation with issuer + audience claims (via PyJWT).

Consumed by auth services and app/api/deps.py. No business logic here.
"""

import uuid
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


# Precomputed Argon2id hash of an arbitrary string. Verifying a submitted
# password against it costs the same as a real check, so login for an unknown
# account is not measurably faster than for a known one (timing side channel).
_DUMMY_PASSWORD_HASH = password_hash.hash("agencyos-dummy-password-for-timing")


def verify_password_dummy(password: str) -> None:
    """Burn the same CPU as a real verify, discarding the result.

    Call when no user (or no password hash) exists so callers cannot tell
    "unknown account" from "wrong password" by response time.
    """
    password_hash.verify(password, _DUMMY_PASSWORD_HASH)


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
    token_version: int = 0,
) -> str:
    """Create a signed JWT for `subject` with iat/exp/iss/aud claims.

    ``token_version`` is embedded as the ``tv`` claim so token revocation can be
    enforced server-side against ``users.token_version`` (see app/api/deps.py).
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "jti": uuid.uuid4().hex,
        "tv": token_version,
        "exp": now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
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


# --- Account-lifecycle tokens (email verification / password reset) ---


def generate_opaque_token() -> str:
    """Generate a high-entropy opaque token (returned to the user once)."""
    return token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    """Return the SHA-256 digest stored for an opaque account token."""
    return sha256(token.encode("utf-8")).hexdigest()
