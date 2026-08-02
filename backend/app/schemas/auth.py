"""Auth API schemas: registration, login, token refresh.

Phase 2 implements first-party email/password auth backed by the JWT
primitives in ``app/core/security.py`` and rotation-based refresh tokens.
"""
from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    """User credentials for login."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    """Payload to create a new organization and its owner account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(
        min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )


class TokenResponse(BaseModel):
    """JWT pair returned after login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class AuthResponse(TokenResponse):
    """Token pair plus the authenticated user (avoids an extra round trip)."""

    user: UserRead


class RefreshRequest(BaseModel):
    """Payload to exchange a refresh token for a new token pair."""

    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    """Payload to change the current user's password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
