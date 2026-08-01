"""Tests for security primitives: password hashing and JWT handling."""
import pytest

from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    require_valid_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("S3cure!pass")
    assert hashed != "S3cure!pass"
    assert verify_password("S3cure!pass", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_roundtrip() -> None:
    token = create_access_token("user-1")
    claims = decode_access_token(token)
    assert claims["sub"] == "user-1"
    assert claims["iss"] == "agencyos"
    assert claims["aud"] == "agencyos-api"


def test_invalid_token_raises_app_error() -> None:
    with pytest.raises(AppError) as exc_info:
        require_valid_token("not-a-valid-jwt")
    assert exc_info.value.status_code == 401
