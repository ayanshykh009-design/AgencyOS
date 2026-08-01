"""Security primitives.

Placeholder module for authentication/authorization helpers:
- password hashing (passlib + bcrypt),
- JWT create/decode (python-jose),
- API-key helpers.

Wire real implementations here and consume them from app/api/deps.py.
No business logic should live in this module.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt  # type: ignore

from app.core.config import settings


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed JWT access token for `subject`.

    Implemented as a placeholder — refine claims (roles, scopes) as needed.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT, returning its claims."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
