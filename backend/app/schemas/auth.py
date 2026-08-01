"""Auth-related request/response schemas (placeholders).

Define the auth API contract before implementing endpoints.
"""
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """User credentials for login."""

    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    """JWT token pair returned after login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Payload for new-user registration."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
