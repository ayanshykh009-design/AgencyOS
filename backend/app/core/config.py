"""Application configuration.

All values come from environment variables / .env files via pydantic-settings.
Rule: configuration flows through this module only — never hardcode secrets.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings for the AgencyOS backend."""

    # Loaded from backend/.env (or process environment).
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- App ---
    APP_NAME: str = "AgencyOS API"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ISSUER: str = "agencyos"
    JWT_AUDIENCE: str = "agencyos-api"
    # Shared secret for inbound webhooks (n8n / contact forms). Endpoints that
    # rely on it refuse to operate when this is empty.
    WEBHOOK_SECRET: str = ""

    # --- Database (local dev mirror of Supabase) ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://agencyos:change-me@localhost:5432/agencyos"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # --- Supabase (managed PostgreSQL) ---
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # --- Redis (shared rate limiting / cache across instances) ---
    REDIS_URL: str = ""

    # --- HTTP hardening ---
    # Comma-separated origins allowed to call this API.
    CORS_ORIGINS: str = "http://localhost:3000"
    # Comma-separated allowed host headers (Host header allow-list).
    TRUSTED_HOSTS: str = "localhost,127.0.0.1"
    SECURITY_HEADERS: bool = True
    ENABLE_CSP: bool = False

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = False
    LOG_FILE_PATH: str = str(BACKEND_DIR.parent / "storage" / "logs" / "backend.log")

    # --- Rate limiting (slowapi) ---
    RATE_LIMIT_DEFAULT: str = "200/minute"
    RATE_LIMIT_STRICT: str = "20/minute"

    # --- CSV import worker ---
    IMPORT_WORKER_ENABLED: bool = True
    IMPORT_CHUNK_SIZE: int = 200
    # Directory for uploaded CSV files (volume-mounted into storage/uploads).
    UPLOAD_DIR: str = str(BACKEND_DIR.parent / "storage" / "uploads")

    # --- Observability (OpenTelemetry) ---
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "agencyos-api"
    OTEL_ENDPOINT: str = ""  # e.g. http://otel-collector:4318/v1/traces

    # --- LLM provider layer (app/llm) ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_PROVIDER: str = "openai"
    LLM_DEFAULT_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_TOKENS: int = 4096
    LLM_DEFAULT_TEMPERATURE: float = 0.7

    # --- n8n automation ---
    N8N_BASE_URL: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list of allowed origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        """Parse TRUSTED_HOSTS into a list of allowed Host headers."""
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    def validate_for_production(self) -> None:
        """Fail fast on dangerous configuration when APP_ENV=production."""
        if self.APP_ENV != "production":
            return
        if self.APP_DEBUG:
            raise RuntimeError("APP_DEBUG must be false in production")
        if self.SECRET_KEY in {"change-me", ""}:
            raise RuntimeError("SECRET_KEY must be overridden in production")
        if not self.DATABASE_URL.startswith(("postgresql", "postgres")):
            raise RuntimeError("DATABASE_URL must be set in production")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (lazy + memoized)."""
    return Settings()


# Convenience singleton used across the app.
settings = get_settings()
