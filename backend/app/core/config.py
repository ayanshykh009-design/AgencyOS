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

    # --- Frontend (used to build invite/share links) ---
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Supabase (managed PostgreSQL) ---
    SUPABASE_URL: str = ""
    # TODO: unused by feature code today (server-side access uses the service
    # role key via get_supabase); reserved for client-facing anon-key flows.
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
    # Content-Security-Policy is restrictive by default; keep it on.
    ENABLE_CSP: bool = True
    # Comma-separated extra connect-src origins for the CSP policy
    # (e.g. Supabase, n8n, an LLM gateway). Validated at startup.
    CSP_CONNECT_ORIGINS: str = ""

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = False
    LOG_FILE_PATH: str = str(BACKEND_DIR.parent / "storage" / "logs" / "backend.log")

    # --- Rate limiting (slowapi) ---
    RATE_LIMIT_DEFAULT: str = "200/minute"
    RATE_LIMIT_STRICT: str = "20/minute"
    # AI endpoints trigger LLM/n8n work — keep them tighter than the default.
    RATE_LIMIT_AI: str = "60/minute"

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
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_MIN_BACKOFF: float = 1.0
    LLM_RETRY_MAX_BACKOFF: float = 30.0

    # --- n8n automation ---
    N8N_BASE_URL: str = ""

    # --- Workflow execution worker ---
    EXECUTION_WORKER_ENABLED: bool = True
    # Max queued executions drained in a single sweep (bounded per poll).
    EXECUTION_BATCH_SIZE: int = 10
    # Sweep cadence: seconds between polls of the queued/retry buckets.
    EXECUTION_POLL_INTERVAL_SECONDS: int = 5
    # Seconds a queued execution may spend in RUNNING before the worker marks
    # it timed out (guards against adapters that hang without raising).
    EXECUTION_TIMEOUT_SECONDS: int = 300
    # Max un-drained (QUEUED + RETRYING) executions per organization. ``queue()``
    # refuses with 409 once the cap is reached; EXECUTION_MANAGE bypasses it.
    EXECUTION_MAX_PENDING_PER_ORG: int = 500
    # Max candidate organizations visited by the fair-drain sweep in one poll;
    # candidates are ordered oldest-first so no org starves the queue.
    EXECUTION_ORGS_PER_SWEEP: int = 20
    # Per-session statement timeout applied to worker sessions (seconds), so a
    # runaway sweep query can never pin a DB connection for long.
    EXECUTION_STATEMENT_TIMEOUT_SECONDS: int = 30

    # --- Execution data retention ---
    # Retention sweep is on by default (bounded DELETE in chunks).
    EXECUTION_RETENTION_ENABLED: bool = True
    # execution_events older than this (days) are deleted by the retention sweep.
    EXECUTION_EVENT_RETENTION_DAYS: int = 90
    # Rows pruned per retention batch (bounds DB + lock time).
    EXECUTION_RETENTION_BATCH: int = 1000
    # Cadence (seconds) between retention sweep ticks.
    EXECUTION_RETENTION_INTERVAL_SECONDS: int = 3600

    # --- Builtin (in-process) execution engine ---
    # Max steps executed across a whole definition (incl. nested branches).
    BUILTIN_MAX_STEPS: int = 50
    # Max nesting depth of condition steps (defense against deep recursion).
    BUILTIN_MAX_CONDITION_DEPTH: int = 3
    # Max length of a single template string evaluated at runtime.
    BUILTIN_MAX_TEMPLATE_LENGTH: int = 4000
    # Max serialized size of the execution result payload (bytes).
    BUILTIN_MAX_RESULT_SIZE_BYTES: int = 524288

    # --- Workflow event fan-out guards ---
    # Max executions a single published event may queue (bounds fan-out; a
    # misconfigured event_type with thousands of triggers is truncated).
    EVENT_FANOUT_MAX_TRIGGERS: int = 100
    # Max serialized size (bytes) of an event payload. The payload is copied
    # into every queued execution's input, so it is capped at publish time.
    EVENT_MAX_PAYLOAD_BYTES: int = 262144

    # --- Schedule dispatcher (worker phase; isolated from the execution queue) ---
    SCHEDULE_DISPATCHER_ENABLED: bool = True
    # Cadence (seconds) between schedule-dispatch sweeps. Queue phases run at
    # EXECUTION_POLL_INTERVAL_SECONDS and are never delayed by this phase.
    SCHEDULE_POLL_INTERVAL_SECONDS: int = 15
    # Max schedule triggers evaluated per sweep (bounds DB + CPU work).
    SCHEDULE_BATCH_LIMIT: int = 100

    # --- Credentials encryption (envelope + key versioning) ---
    # Current master key used to encrypt new credential values.
    CREDENTIALS_ENC_KEY: str = ""
    # Retiring master key during rotation (dual-read until rekey completes).
    # Its version label is CREDENTIAL_KEY_VERSION - 1.
    CREDENTIALS_ENC_KEY_PREVIOUS: str = ""
    # Version label of CREDENTIALS_ENC_KEY (positive integer; bump on rotation).
    CREDENTIAL_KEY_VERSION: str = "1"
    # Rekey worker: re-encrypts stale credentials with the current key.
    CREDENTIAL_REKEY_ENABLED: bool = False
    # Max rows re-encrypted per sweep (bounds DB + CPU work).
    CREDENTIAL_REKEY_BATCH: int = 100
    # Cadence (seconds) between rekey sweeps.
    CREDENTIAL_REKEY_INTERVAL_SECONDS: int = 3600

    # --- Phase 5D AI Intelligence Layer (foundation) ---
    # Feature flags gate each Phase 5D subsystem. Defaults are OFF until a
    # subsystem ships and passes its quality gate; consumers must treat an
    # OFF flag as "feature unavailable" (fail closed).
    AGENT_RUNTIME_ENABLED: bool = False
    AI_MEMORY_ENABLED: bool = False
    COMMUNICATION_LAYER_ENABLED: bool = False
    GROWTH_AGENT_ENABLED: bool = False

    # Bounds on the Phase 5D data lifecycle. Recorded in M1 so the design
    # defaults stay config-driven once each subsystem ships (see the approved
    # Phase 5D documentation: database design / communication layer).
    # Working memory (conversation / research / workflow / shared context) is
    # ephemeral: entries older than this are eligible for TTL cleanup.
    MEMORY_WORKING_TTL_DAYS: int = 30
    # Memory TTL cleanup worker (M4): deletes ONLY expired working memories in
    # bounded, idempotent, org-scoped batches. Long-term memory is never pruned.
    MEMORY_CLEANUP_ENABLED: bool = True
    # Cadence (seconds) between working-memory TTL cleanup sweeps.
    MEMORY_CLEANUP_INTERVAL_SECONDS: int = 3600
    # Max expired working memories deleted per sweep tick (bounds DB + lock time).
    MEMORY_CLEANUP_BATCH_SIZE: int = 500
    # Bounds the memory context injected into the AI system prompt (M4).
    MEMORY_CONTEXT_MAX_CHARS: int = 2500
    # Max memories/knowledge returned by one memory retrieval for the AI path.
    MEMORY_RETRIEVAL_LIMIT: int = 10
    # In-app notifications are pruned after this many days.
    NOTIFICATION_RETENTION_DAYS: int = 90
    # Approval requests auto-expire (deny) after this many hours.
    APPROVAL_EXPIRY_HOURS: int = 24
    # Growth metrics rows are pruned after this many days (36 months).
    GROWTH_METRICS_RETENTION_DAYS: int = 1095
    # Agent run records are pruned after this many days (configurable).
    AGENT_RUN_RETENTION_DAYS: int = 90

    # --- M5 Agent Runtime worker ---
    # Sweep cadence: seconds between polls of the queued agent-run buckets.
    AGENT_RUN_POLL_INTERVAL_SECONDS: int = 5
    # Max queued runs drained in a single sweep (bounded per poll).
    AGENT_RUN_BATCH_SIZE: int = 10
    # Max candidate organizations visited by the fair-drain sweep in one poll.
    AGENT_RUN_ORGS_PER_SWEEP: int = 20
    # Seconds a running agent run may spend before the worker re-converges it
    # as failed (guards against executors that hang without raising).
    AGENT_RUN_TIMEOUT_SECONDS: int = 300

    # --- M6 Founder Communication & Delivery Layer ---
    # Feature flag for the delivery subsystem.
    DELIVERY_ENABLED: bool = True
    # Max queued deliveries drained in a single sweep (bounded per poll).
    DELIVERY_BATCH_SIZE: int = 10
    # Sweep cadence: seconds between polls of the queued/retry buckets.
    DELIVERY_POLL_INTERVAL_SECONDS: int = 5
    # Active provider timeout (seconds). Hard limit on provider dispatch.
    DELIVERY_ACTIVE_TIMEOUT_SECONDS: int = 30
    # Stale worker recovery window (seconds). A PROCESSING row older than this
    # is re-queued by the recovery sweep. Must be > DELIVERY_ACTIVE_TIMEOUT_SECONDS.
    DELIVERY_RECOVERY_SECONDS: int = 300
    # Max undrained (QUEUED + PROCESSING) deliveries per organization.
    DELIVERY_MAX_PENDING_PER_ORG: int = 500
    # Max candidate organizations visited by the fair-drain sweep in one poll.
    DELIVERY_ORGS_PER_SWEEP: int = 20
    # Default max delivery attempts.
    DELIVERY_MAX_ATTEMPTS: int = 4
    # Retry backoff base seconds: 10s, 20s, 40s (exponential).
    DELIVERY_RETRY_BASE_SECONDS: int = 10
    # Max serialized delivery payload size (bytes); 0 disables the check.
    DELIVERY_MAX_PAYLOAD_BYTES: int = 65536
    # Per-session statement timeout applied to worker sessions (seconds).
    DELIVERY_STATEMENT_TIMEOUT_SECONDS: int = 30
    # Delivery event retention (days).
    DELIVERY_EVENT_RETENTION_DAYS: int = 90
    # Delivery event retention batch size.
    DELIVERY_RETENTION_BATCH: int = 1000
    # Cadence (seconds) between retention sweep ticks.
    DELIVERY_RETENTION_INTERVAL_SECONDS: int = 3600
    # Feature flag: prune old delivery_events rows.
    DELIVERY_RETENTION_ENABLED: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list of allowed origins."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        """Parse TRUSTED_HOSTS into a list of allowed Host headers."""
        return [h.strip() for h in self.TRUSTED_HOSTS.split(",") if h.strip()]

    def _validate_redis_url(self) -> None:
        if not self.REDIS_URL:
            return
        if not self.REDIS_URL.startswith(("redis://", "rediss://")):
            raise RuntimeError("REDIS_URL must use the redis:// or rediss:// scheme")

    def _validate_enc_key(self) -> None:
        if self.APP_ENV == "production" and not self.CREDENTIALS_ENC_KEY:
            raise RuntimeError("CREDENTIALS_ENC_KEY must be set in production")
        if not self.CREDENTIAL_KEY_VERSION.isdigit() or int(self.CREDENTIAL_KEY_VERSION) < 1:
            raise RuntimeError("CREDENTIAL_KEY_VERSION must be a positive integer")
        if self.CREDENTIALS_ENC_KEY_PREVIOUS and int(self.CREDENTIAL_KEY_VERSION) < 2:
            raise RuntimeError(
                "CREDENTIALS_ENC_KEY_PREVIOUS requires CREDENTIAL_KEY_VERSION >= 2"
            )
        if self.CREDENTIAL_REKEY_BATCH < 1:
            raise RuntimeError("CREDENTIAL_REKEY_BATCH must be >= 1")
        if self.CREDENTIAL_REKEY_INTERVAL_SECONDS < 1:
            raise RuntimeError("CREDENTIAL_REKEY_INTERVAL_SECONDS must be >= 1")
        if self.BUILTIN_MAX_STEPS < 1:
            raise RuntimeError("BUILTIN_MAX_STEPS must be >= 1")
        if self.BUILTIN_MAX_CONDITION_DEPTH < 1:
            raise RuntimeError("BUILTIN_MAX_CONDITION_DEPTH must be >= 1")
        if self.BUILTIN_MAX_TEMPLATE_LENGTH < 1:
            raise RuntimeError("BUILTIN_MAX_TEMPLATE_LENGTH must be >= 1")
        if self.BUILTIN_MAX_RESULT_SIZE_BYTES < 1:
            raise RuntimeError("BUILTIN_MAX_RESULT_SIZE_BYTES must be >= 1")
        if self.EVENT_FANOUT_MAX_TRIGGERS < 1:
            raise RuntimeError("EVENT_FANOUT_MAX_TRIGGERS must be >= 1")
        if self.EVENT_MAX_PAYLOAD_BYTES < 1:
            raise RuntimeError("EVENT_MAX_PAYLOAD_BYTES must be >= 1")
        if self.EXECUTION_BATCH_SIZE < 1:
            raise RuntimeError("EXECUTION_BATCH_SIZE must be >= 1")
        if self.EXECUTION_ORGS_PER_SWEEP < 1:
            raise RuntimeError("EXECUTION_ORGS_PER_SWEEP must be >= 1")
        if self.EXECUTION_MAX_PENDING_PER_ORG < 1:
            raise RuntimeError("EXECUTION_MAX_PENDING_PER_ORG must be >= 1")
        if self.EXECUTION_STATEMENT_TIMEOUT_SECONDS < 1:
            raise RuntimeError("EXECUTION_STATEMENT_TIMEOUT_SECONDS must be >= 1")
        if self.EXECUTION_EVENT_RETENTION_DAYS < 1:
            raise RuntimeError("EXECUTION_EVENT_RETENTION_DAYS must be >= 1")
        if self.EXECUTION_RETENTION_BATCH < 1:
            raise RuntimeError("EXECUTION_RETENTION_BATCH must be >= 1")
        if self.EXECUTION_RETENTION_INTERVAL_SECONDS < 1:
            raise RuntimeError("EXECUTION_RETENTION_INTERVAL_SECONDS must be >= 1")

    def _validate_phase5d(self) -> None:
        if self.MEMORY_WORKING_TTL_DAYS < 1:
            raise RuntimeError("MEMORY_WORKING_TTL_DAYS must be >= 1")
        if self.MEMORY_CLEANUP_INTERVAL_SECONDS < 60:
            raise RuntimeError("MEMORY_CLEANUP_INTERVAL_SECONDS must be >= 60")
        if self.MEMORY_CLEANUP_BATCH_SIZE < 1:
            raise RuntimeError("MEMORY_CLEANUP_BATCH_SIZE must be >= 1")
        if self.MEMORY_CONTEXT_MAX_CHARS < 500:
            raise RuntimeError("MEMORY_CONTEXT_MAX_CHARS must be >= 500")
        if self.MEMORY_RETRIEVAL_LIMIT < 1:
            raise RuntimeError("MEMORY_RETRIEVAL_LIMIT must be >= 1")
        if self.NOTIFICATION_RETENTION_DAYS < 1:
            raise RuntimeError("NOTIFICATION_RETENTION_DAYS must be >= 1")
        if self.APPROVAL_EXPIRY_HOURS < 1:
            raise RuntimeError("APPROVAL_EXPIRY_HOURS must be >= 1")
        if self.GROWTH_METRICS_RETENTION_DAYS < 1:
            raise RuntimeError("GROWTH_METRICS_RETENTION_DAYS must be >= 1")
        if self.AGENT_RUN_RETENTION_DAYS < 1:
            raise RuntimeError("AGENT_RUN_RETENTION_DAYS must be >= 1")
        if self.AGENT_RUN_POLL_INTERVAL_SECONDS < 1:
            raise RuntimeError("AGENT_RUN_POLL_INTERVAL_SECONDS must be >= 1")
        if self.AGENT_RUN_BATCH_SIZE < 1:
            raise RuntimeError("AGENT_RUN_BATCH_SIZE must be >= 1")
        if self.AGENT_RUN_ORGS_PER_SWEEP < 1:
            raise RuntimeError("AGENT_RUN_ORGS_PER_SWEEP must be >= 1")
        if self.AGENT_RUN_TIMEOUT_SECONDS < 1:
            raise RuntimeError("AGENT_RUN_TIMEOUT_SECONDS must be >= 1")

    def _validate_m6_delivery(self) -> None:
        if self.DELIVERY_BATCH_SIZE < 1:
            raise RuntimeError("DELIVERY_BATCH_SIZE must be >= 1")
        if self.DELIVERY_ORGS_PER_SWEEP < 1:
            raise RuntimeError("DELIVERY_ORGS_PER_SWEEP must be >= 1")
        if self.DELIVERY_MAX_PENDING_PER_ORG < 1:
            raise RuntimeError("DELIVERY_MAX_PENDING_PER_ORG must be >= 1")
        if self.DELIVERY_STATEMENT_TIMEOUT_SECONDS < 1:
            raise RuntimeError("DELIVERY_STATEMENT_TIMEOUT_SECONDS must be >= 1")
        if self.DELIVERY_ACTIVE_TIMEOUT_SECONDS < 1:
            raise RuntimeError("DELIVERY_ACTIVE_TIMEOUT_SECONDS must be >= 1")
        if self.DELIVERY_RECOVERY_SECONDS < 1:
            raise RuntimeError("DELIVERY_RECOVERY_SECONDS must be >= 1")
        if self.DELIVERY_MAX_ATTEMPTS < 1:
            raise RuntimeError("DELIVERY_MAX_ATTEMPTS must be >= 1")
        if self.DELIVERY_RETRY_BASE_SECONDS < 1:
            raise RuntimeError("DELIVERY_RETRY_BASE_SECONDS must be >= 1")
        if self.DELIVERY_MAX_PAYLOAD_BYTES < 0:
            raise RuntimeError("DELIVERY_MAX_PAYLOAD_BYTES must be >= 0")
        if self.DELIVERY_EVENT_RETENTION_DAYS < 1:
            raise RuntimeError("DELIVERY_EVENT_RETENTION_DAYS must be >= 1")
        if self.DELIVERY_RETENTION_BATCH < 1:
            raise RuntimeError("DELIVERY_RETENTION_BATCH must be >= 1")
        if self.DELIVERY_RETENTION_INTERVAL_SECONDS < 1:
            raise RuntimeError("DELIVERY_RETENTION_INTERVAL_SECONDS must be >= 1")
        if self.DELIVERY_RECOVERY_SECONDS <= self.DELIVERY_ACTIVE_TIMEOUT_SECONDS:
            raise RuntimeError(
                "DELIVERY_RECOVERY_SECONDS must be > DELIVERY_ACTIVE_TIMEOUT_SECONDS"
            )

    def _validate_csp(self) -> None:
        # Lazy import: csp.py reads this module's settings singleton, so it
        # cannot be imported at module load time without a cycle.
        from app.core.csp import validate_csp_origins

        try:
            validate_csp_origins(self.CSP_CONNECT_ORIGINS)
        except ValueError as exc:
            raise RuntimeError(f"CSP configuration error: {exc}") from exc

    def validate_runtime(self) -> None:
        """Environment-agnostic startup validation (called on every boot)."""
        self._validate_redis_url()
        self._validate_enc_key()
        self._validate_phase5d()
        self._validate_m6_delivery()
        self._validate_csp()

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
        if not self.ENABLE_CSP:
            raise RuntimeError("ENABLE_CSP must be enabled in production")
        self._validate_redis_url()
        self._validate_enc_key()
        self._validate_phase5d()
        self._validate_m6_delivery()
        self._validate_csp()


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (lazy + memoized)."""
    return Settings()


# Convenience singleton used across the app.
settings = get_settings()
