"""Application configuration.

All values come from environment variables / .env files via pydantic-settings.
Rule: configuration flows through this module only — never hardcode secrets.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the AgencyOS backend."""

    # Loaded from backend/.env (or process environment).
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    APP_NAME: str = "AgencyOS API"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # --- Database (local dev mirror of Supabase) ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://agencyos:change-me@localhost:5432/agencyos"
    )

    # --- Supabase (managed PostgreSQL) ---
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # --- CORS ---
    # Comma-separated string, e.g. "http://localhost:3000,https://app.example.com"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS_ORIGINS into a list of allowed origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (lazy + memoized)."""
    return Settings()


# Convenience singleton used across the app.
settings = get_settings()
